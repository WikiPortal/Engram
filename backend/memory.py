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
    Filter, FieldCondition, MatchValue,
    SparseVectorParams, SparseIndexParams,
    SparseVector,
)
from embedder import embedder
from config import get_settings

settings = get_settings()

SPARSE_FIELD = "text_sparse" 


def _get_client() -> QdrantClient:
    return get_qdrant()


def _tokenize(text: str) -> SparseVector:
    """
    Whitespace tokenizer → SparseVector for Qdrant BM42 index.
    Maps token hashes to normalised term frequencies.
    """
    tokens = text.lower().split()
    tf: dict[int, float] = {}
    for token in tokens:
        h = abs(hash(token)) % (2 ** 31)
        tf[h] = tf.get(h, 0.0) + 1.0
    total = sum(tf.values()) or 1.0
    return SparseVector(
        indices=list(tf.keys()),
        values=[v / total for v in tf.values()],
    )


def _ensure_collection(client: QdrantClient):
    """
    Ensure the Qdrant collection exists with the correct schema.

    On first run (collection missing): creates with dense vectors + payload
    indexes for user_id, is_latest, is_valid. Attempts to also add sparse
    vector config; if the Qdrant version doesn't support it, continues
    without sparse (search falls back to vector-only via RRF).

    On subsequent runs (collection exists): ensures payload indexes exist
    (idempotent — Qdrant ignores create_payload_index if already present).
    Does NOT attempt to modify vector config on existing collections since
    Qdrant does not support changing vector schema after creation.
    """
    from qdrant_client.models import PayloadSchemaType

    existing = [c.name for c in client.get_collections().collections]

    if settings.qdrant_collection not in existing:
        try:
            client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(
                    size=settings.embedding_dim,
                    distance=Distance.COSINE,
                ),
                sparse_vectors_config={
                    SPARSE_FIELD: SparseVectorParams(
                        index=SparseIndexParams(on_disk=False),
                    )
                },
            )
            print(f"[Engram] Created collection '{settings.qdrant_collection}' "
                  f"with dense + sparse/{SPARSE_FIELD}")
        except Exception:
            client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(
                    size=settings.embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            print(f"[Engram] Created collection '{settings.qdrant_collection}' "
                  f"(dense only — upgrade Qdrant for sparse search)")

    _ensure_payload_indexes(client)


def _ensure_payload_indexes(client: QdrantClient):
    """
    Create payload indexes for the fields used in every search filter.
    Qdrant requires indexes on payload fields used in filters.
    Safe to call multiple times — existing indexes are left untouched.
    """
    from qdrant_client.models import PayloadSchemaType

    indexes = [
        ("user_id",   PayloadSchemaType.KEYWORD),
        ("is_latest", PayloadSchemaType.BOOL),
        ("is_valid",  PayloadSchemaType.BOOL),
    ]
    for field, schema_type in indexes:
        try:
            client.create_payload_index(
                collection_name=settings.qdrant_collection,
                field_name=field,
                field_schema=schema_type,
            )
        except Exception:
            pass  


def _collection_has_sparse(client: QdrantClient) -> bool:
    """Return True if the collection has the sparse vector field configured."""
    try:
        info = client.get_collection(settings.qdrant_collection)
        sparse_configs = getattr(info.config.params, "sparse_vectors", None) or {}
        return SPARSE_FIELD in sparse_configs
    except Exception:
        return False


def store(content: str, user_id: str = "default", tags: list[str] = []) -> str:
    """
    Store a memory. Upserts both dense and sparse vectors when available.
    Falls back to dense-only if the sparse field is not yet in the collection.
    Returns the memory ID.
    """
    client = _get_client()
    _ensure_collection(client)

    memory_id    = str(uuid.uuid4())
    dense_vector = embedder.embed(content)

    if _collection_has_sparse(client):
        sparse_vec = _tokenize(content)
        vector = {
            "": dense_vector,         
            SPARSE_FIELD: sparse_vec,  
        }
    else:
        print(f"[Engram] Storing dense-only for [{content[:40]}] — sparse field unavailable")
        vector = dense_vector

    client.upsert(
        collection_name=settings.qdrant_collection,
        points=[PointStruct(
            id=memory_id,
            vector=vector,
            payload={
                "content":    content,
                "user_id":    user_id,
                "tags":       tags,
                "is_latest":  True,
                "is_valid":   True,
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
            FieldCondition(key="is_valid",  match=MatchValue(value=True)),
        ]),
        limit=top_k,
        with_payload=True,
    )

    return [
        {
            "id":         str(r.id),
            "content":    r.payload["content"],
            "score":      round(r.score, 4),
            "tags":       r.payload.get("tags", []),
            "created_at": r.payload.get("created_at", ""),
        }
        for r in results
    ]