"""
Engram — FastAPI Server

  POST   /memory/store          — full ingestion pipeline (brain.remember)
  POST   /memory/recall         — full retrieval pipeline (brain.recall)
  POST   /chat                  — memory-augmented chat   (brain.chat)
  GET    /memory/list/{user_id} — list all memories for a user
  DELETE /memory/{memory_id}    — invalidate a memory (soft delete)
  GET    /health                — service health check

Run:
  cd backend
  uvicorn api:app --host 0.0.0.0 --port 8000 --reload

  Or from project root:
  uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

import brain
from contradiction import invalidate_memory
from graph import get_graph_stats
from memory import recall as _raw_recall
from config import get_settings

settings = get_settings()

# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title="Engram",
    description="Private, self-hosted AI memory layer",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten this for production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────

class StoreRequest(BaseModel):
    content: str = Field(..., description="Raw text to store as memories")
    user_id: str = Field("default", description="User namespace")
    tags: list[str] = Field(default_factory=list, description="Optional tags")


class StoreResponse(BaseModel):
    stored: int
    skipped_duplicates: int
    contradictions_resolved: int
    graph_edges: int
    facts: list[str]


class RecallRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    user_id: str = Field("default")


class MemoryItem(BaseModel):
    id: str
    content: str
    score: Optional[float] = None
    rerank_score: Optional[float] = None
    tags: list[str] = []
    created_at: Optional[str] = None
    graph_rel: Optional[str] = None     # set when result came from graph expansion


class RecallResponse(BaseModel):
    query: str
    memories: list[MemoryItem]
    total_found: int
    context_tokens: int


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    user_id: str = Field("default")
    history: list[dict] = Field(
        default_factory=list,
        description='Conversation history: [{"role": "user"|"model", "content": "..."}]'
    )


class ChatResponse(BaseModel):
    response: str
    memories_used: int


class MemoryListItem(BaseModel):
    id: str
    content: str
    tags: list[str] = []
    created_at: Optional[str] = None
    is_valid: bool = True
    is_latest: bool = True


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    graph: dict


# ── Endpoints ─────────────────────────────────────────────────────

@app.post("/memory/store", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
def store_memory(req: StoreRequest):
    """
    Run the full ingestion pipeline on raw text.
    Extracts atomic facts, deduplicates, resolves contradictions,
    sets TTL, and links in the knowledge graph.
    """
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content cannot be empty")
    try:
        result = brain.remember(req.content, user_id=req.user_id, tags=req.tags)
        return StoreResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/memory/recall", response_model=RecallResponse)
def recall_memories(req: RecallRequest):
    """
    Run the full retrieval pipeline.
    HyDE expansion → hybrid search → graph expansion → rerank → context guard.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")
    try:
        result = brain.recall(req.query, user_id=req.user_id)
        memories = [MemoryItem(**m) for m in result["memories"]]
        return RecallResponse(
            query=result["query"],
            memories=memories,
            total_found=result["total_found"],
            context_tokens=result["context_tokens"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """
    Memory-augmented chat.
    1. Recall relevant memories (for context + badge count)
    2. Generate response via Gemini
    3. Restore PII tokens in the response so the user sees real names
    4. Store the conversation turn as a new memory (fire-and-forget)
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    try:
        import pii as _pii
        import threading

        # Step 1 — recall count for badge
        recall_result = brain.recall(req.message, user_id=req.user_id)
        memories_used = len(recall_result["memories"])

        # Step 2 — generate response
        response_text = brain.chat(
            req.message,
            user_id=req.user_id,
            history=req.history,
        )

        # Step 3 — restore PII tokens so user sees real names
        response_text = _pii.restore(response_text)

        # Step 4 — store turn as memory (background thread, non-blocking)
        def _store_turn():
            try:
                turn = f"User: {req.message}\nAssistant: {response_text}"
                brain.remember(turn, user_id=req.user_id, tags=["conversation"])
            except Exception as e:
                print(f"[Engram] Background store failed (non-critical): {e}")

        threading.Thread(target=_store_turn, daemon=True).start()

        return ChatResponse(response=response_text, memories_used=memories_used)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory/list/{user_id}", response_model=list[MemoryListItem])
def list_memories(user_id: str, limit: int = 50):
    """
    List all valid memories for a user, most recent first.
    Query param: limit (default 50, max 500).
    """
    limit = min(limit, 500)
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

        existing = [c.name for c in client.get_collections().collections]
        if settings.qdrant_collection not in existing:
            return []

        results, _ = client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=Filter(must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="is_latest", match=MatchValue(value=True)),
                FieldCondition(key="is_valid", match=MatchValue(value=True)),
            ]),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        memories = [
            MemoryListItem(
                id=str(r.id),
                content=r.payload["content"],
                tags=r.payload.get("tags", []),
                created_at=r.payload.get("created_at"),
                is_valid=r.payload.get("is_valid", True),
                is_latest=r.payload.get("is_latest", True),
            )
            for r in results
        ]

        # Sort by created_at descending (most recent first)
        memories.sort(key=lambda m: m.created_at or "", reverse=True)
        return memories

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/memory/{memory_id}", status_code=status.HTTP_200_OK)
def delete_memory(memory_id: str):
    """
    Soft-delete (invalidate) a memory.
    Marks is_valid=False, is_latest=False in Qdrant.
    Logs to PostgreSQL audit trail.
    Paper note: prefer invalidation over hard delete to preserve audit history.
    """
    try:
        invalidate_memory(memory_id, reason="User-requested deletion via API")
        return {"memory_id": memory_id, "status": "invalidated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health", response_model=HealthResponse)
def health():
    """
    Service health check.
    Returns status, timestamp, and graph stats for the default user.
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat() + "Z",
        graph=get_graph_stats(),
    )
