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
  python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Request, Depends, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import brain
from contradiction import invalidate_memory
from graph import get_graph_stats
from config import get_settings
from auth import router as auth_router, get_optional_user

settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[])

app = FastAPI(
    title="Engram",
    description="Private, self-hosted AI memory layer",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Auth routes: /auth/register, /auth/login, /auth/me
app.include_router(auth_router)


class EngramError(Exception):
    """Structured error with HTTP status and clean user message."""
    def __init__(self, status_code: int, message: str, detail: str = ""):
        self.status_code = status_code
        self.message = message
        self.detail = detail
        super().__init__(message)


def classify_error(e: Exception) -> EngramError:
    """
    Turn any exception into a clean EngramError with a human-readable message.
    Handles Gemini quota errors, connection failures, and generic errors.
    """
    raw = str(e)

    if "429" in raw or "quota" in raw.lower() or "rate" in raw.lower():
        retry_match = re.search(r'retry.*?(\d+)\s*s', raw, re.IGNORECASE)
        retry_hint = ""
        if retry_match:
            secs = int(retry_match.group(1))
            if secs < 60:
                retry_hint = f" Try again in {secs} seconds."
            else:
                mins = round(secs / 60)
                retry_hint = f" Try again in ~{mins} minute{'s' if mins != 1 else ''}."

        if "per_day" in raw.lower() or "PerDay" in raw or "daily" in raw.lower():
            return EngramError(
                429,
                f"Daily AI quota reached.{retry_hint} The free Gemini tier allows 20 requests/day. "
                "Update GEMINI_MODEL in .env to use a different model, or wait until midnight PT for reset.",
                "QUOTA_DAILY"
            )
        return EngramError(
            429,
            f"AI rate limit hit.{retry_hint} The free Gemini tier allows 5 requests/minute. "
            "Wait a moment and try again.",
            "QUOTA_RPM"
        )

    if "not found" in raw.lower() and "model" in raw.lower():
        from llm import get_provider, get_model
        return EngramError(
            502,
            f"AI model '{get_model()}' not found for provider '{get_provider()}'. "
            "Check LLM_MODEL in your .env or remove it to use the provider default.",
            "MODEL_NOT_FOUND"
        )

    if "api_key" in raw.lower() or "401" in raw or "403" in raw or "invalid" in raw.lower() and "key" in raw.lower():
        return EngramError(
            401,
            "Gemini API key is invalid or missing. Set GEMINI_API_KEY in backend/.env.",
            "AUTH_ERROR"
        )

    if "connection refused" in raw.lower() or "connect" in raw.lower() and ("qdrant" in raw.lower() or "redis" in raw.lower() or "postgres" in raw.lower()):
        return EngramError(
            503,
            "Cannot reach one or more databases. Make sure Docker is running: docker compose up -d",
            "DB_UNAVAILABLE"
        )

    if "qdrant" in raw.lower():
        return EngramError(503, "Vector database (Qdrant) is unavailable. Run: docker compose up -d", "QDRANT_DOWN")

    if "redis" in raw.lower():
        return EngramError(503, "Cache database (Redis) is unavailable. Run: docker compose up -d", "REDIS_DOWN")

    if "psycopg2" in raw.lower() or "postgres" in raw.lower():
        return EngramError(503, "PostgreSQL database is unavailable. Run: docker compose up -d", "POSTGRES_DOWN")

    if "safety" in raw.lower() or "blocked" in raw.lower() or "SAFETY" in raw:
        return EngramError(
            422,
            "The AI blocked this message due to safety filters. Try rephrasing.",
            "CONTENT_BLOCKED"
        )

    if "json" in raw.lower() and ("decode" in raw.lower() or "parse" in raw.lower()):
        return EngramError(
            502,
            "The AI returned an unexpected response format. This is usually transient — try again.",
            "LLM_PARSE_ERROR"
        )

    return EngramError(500, f"An unexpected error occurred: {raw[:200]}", "INTERNAL_ERROR")


@app.exception_handler(EngramError)
async def engram_error_handler(request: Request, exc: EngramError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "code": exc.detail,
            "status": exc.status_code,
        }
    )


def handle(e: Exception) -> None:
    """Classify and raise as EngramError. Call from every except block."""
    err = classify_error(e)
    raise err


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
    graph_rel: Optional[str] = None


class RecallResponse(BaseModel):
    query: str
    memories: list[MemoryItem]
    total_found: int
    context_tokens: int


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    user_id: str = Field("default")
    history: list[dict] = Field(default_factory=list)


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
    model: str
    graph: dict


@app.post("/memory/store", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_store)
def store_memory(req: StoreRequest, request: Request, current_user: dict = Depends(get_optional_user)):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content cannot be empty")
    user_id = current_user["sub"] if current_user else req.user_id
    try:
        result = brain.remember(req.content, user_id=user_id, tags=req.tags)
        return StoreResponse(**result)
    except EngramError:
        raise
    except Exception as e:
        handle(e)


@app.post("/memory/recall", response_model=RecallResponse)
@limiter.limit(settings.rate_limit_recall)
def recall_memories(req: RecallRequest, request: Request, current_user: dict = Depends(get_optional_user)):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")
    user_id = current_user["sub"] if current_user else req.user_id
    try:
        result = brain.recall(req.query, user_id=user_id)
        memories = [MemoryItem(**m) for m in result["memories"]]
        return RecallResponse(
            query=result["query"],
            memories=memories,
            total_found=result["total_found"],
            context_tokens=result["context_tokens"],
        )
    except EngramError:
        raise
    except Exception as e:
        handle(e)


def _store_conversation_turn(user_message: str, assistant_response: str, user_id: str) -> None:
    """
    Persist a conversation turn as a memory.
    Called via FastAPI BackgroundTasks — runs after the response is sent,
    inside the same process, managed by uvicorn's event loop.

    Why BackgroundTasks instead of daemon threads:
      - Daemon threads are fire-and-forget with no lifecycle management.
        If the server shuts down mid-thread, the write is silently lost.
      - BackgroundTasks run within uvicorn's request lifecycle. On graceful
        shutdown uvicorn drains in-flight background tasks before exiting.
      - No new dependency required (BackgroundTasks is built into FastAPI).

    Note: for true at-least-once delivery across crashes, graduate this to
    a persistent task queue (ARQ + Redis or Celery). That is Step 6.
    """
    try:
        turn = f"User: {user_message}\nAssistant: {assistant_response}"
        brain.remember(turn, user_id=user_id, tags=["conversation"])
        print(f"[Engram] Conversation turn stored for user [{user_id[:8]}]")
    except Exception as e:
        print(f"[Engram] Background turn store failed (non-critical): {e}")


@app.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.rate_limit_chat)
def chat(
    req: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_optional_user),
):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")
    try:
        import pii as _pii

        user_id = current_user["sub"] if current_user else req.user_id

        # Recall relevant memories (also used for badge count)
        recall_result = brain.recall(req.message, user_id=user_id)
        memories_used = len(recall_result["memories"])

        # Generate response
        response_text = brain.chat(
            req.message,
            user_id=user_id,
            history=req.history,
        )

        # Restore any PII tokens that were masked before storage
        response_text = _pii.restore(response_text)

        # Store turn after response is sent — non-blocking, lifecycle-managed
        background_tasks.add_task(
            _store_conversation_turn,
            user_message=req.message,
            assistant_response=response_text,
            user_id=user_id,
        )

        return ChatResponse(response=response_text, memories_used=memories_used)

    except EngramError:
        raise
    except Exception as e:
        handle(e)


@app.get("/memory/list/{user_id}", response_model=list[MemoryListItem])
@limiter.limit(settings.rate_limit_recall)
def list_memories(user_id: str, request: Request, limit: int = 50, current_user: dict = Depends(get_optional_user)):
    if current_user and current_user["sub"] != user_id:
        raise HTTPException(403, "Cannot access another user's memories")
    limit = min(limit, 500)
    try:
        from db import get_qdrant
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = get_qdrant()
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
        memories.sort(key=lambda m: m.created_at or "", reverse=True)
        return memories

    except EngramError:
        raise
    except Exception as e:
        handle(e)


@app.delete("/memory/{memory_id}", status_code=status.HTTP_200_OK)
@limiter.limit(settings.rate_limit_store)
def delete_memory(memory_id: str, request: Request):
    try:
        invalidate_memory(memory_id, reason="User-requested deletion via API")
        return {"memory_id": memory_id, "status": "invalidated"}
    except EngramError:
        raise
    except Exception as e:
        handle(e)


@app.get("/health", response_model=HealthResponse)
def health():
    from llm import provider_info
    info = provider_info()
    return HealthResponse(
        status="ok",
        timestamp=datetime.utcnow().isoformat() + "Z",
        model=f"{info['provider']}/{info['model']}",
        graph=get_graph_stats(),
    )
