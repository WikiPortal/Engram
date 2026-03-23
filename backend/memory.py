"""
Engram — Memory Store & Recall (Step 5)
Basic version: store → embed → Qdrant | recall → embed → search
"""
import uuid
from datetime import datetime
from db import get_qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)
from embedder import embedder
from config import get_settings

settings = get_settings()


def _get_client() -> QdrantClient:
    return get_qdrant()


def _ensure_collection(client: QdrantClient):
    """Create collection if it doesn't exist yet."""
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dim,
                distance=Distance.COSINE
            )
        )
        print(f"[Engram] Created collection: {settings.qdrant_collection}")


def store(content: str, user_id: str = "default", tags: list[str] = []) -> str:
    """
    Store a memory.
    Returns the memory ID.
    """
    client = _get_client()
    _ensure_collection(client)

    memory_id = str(uuid.uuid4())
    vector = embedder.embed(content)

    client.upsert(
        collection_name=settings.qdrant_collection,
        points=[PointStruct(
            id=memory_id,
            vector=vector,
            payload={
                "content": content,
                "user_id": user_id,
                "tags": tags,
                "is_latest": True,
                "is_valid": True,
                "created_at": datetime.utcnow().isoformat(),
            }
        )]
    )

    print(f"[Engram] Stored [{memory_id[:8]}]: {content[:60]}")
    return memory_id


def recall(query: str, user_id: str = "default", top_k: int = 5) -> list[dict]:
    """
    Recall memories relevant to a query.
    Returns top_k most similar memories.
    """
    client = _get_client()
    _ensure_collection(client)

    query_vector = embedder.embed(query)

    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        query_filter=Filter(must=[
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            FieldCondition(key="is_latest", match=MatchValue(value=True)),
            FieldCondition(key="is_valid", match=MatchValue(value=True)),
        ]),
        limit=top_k,
        with_payload=True
    )

    return [
        {
            "id": str(r.id),
            "content": r.payload["content"],
            "score": round(r.score, 4),
            "tags": r.payload.get("tags", []),
            "created_at": r.payload.get("created_at", ""),
        }
        for r in results
    ]