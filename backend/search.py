"""
Engram — Hybrid Search
Combines dense vector search + sparse keyword search (BM42 via Qdrant).
Merges results via Reciprocal Rank Fusion (RRF).
"""
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue,
    NamedVector, NamedSparseVector, SparseVector,
    SearchRequest,
)
from db import get_qdrant
from embedder import embedder
from config import get_settings

settings = get_settings()

SPARSE_FIELD = "text_sparse"


# ── Dense vector search ───────────────────────────────────────────

def _vector_search(query: str, user_id: str, top_k: int) -> list[dict]:
    """Dense vector similarity search via Qdrant."""
    client = get_qdrant()
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
            "id":           str(r.id),
            "content":      r.payload["content"],
            "tags":         r.payload.get("tags", []),
            "created_at":   r.payload.get("created_at", ""),
            "vector_score": round(r.score, 4),
        }
        for r in results
    ]


# ── Sparse keyword search (BM42 / Qdrant native) ──────────────────

def _tokenize(text: str) -> dict[int, float]:
    """
    Minimal whitespace tokenizer → sparse vector format.
    Maps each unique token to a term frequency weight.
    Qdrant's BM42 index handles IDF weighting internally.

    Returns {token_hash: tf_weight} suitable for SparseVector.
    """
    tokens = text.lower().split()
    tf: dict[int, float] = {}
    for token in tokens:
        h = abs(hash(token)) % (2 ** 31) 
        tf[h] = tf.get(h, 0.0) + 1.0
    total = sum(tf.values()) or 1.0
    return {idx: count / total for idx, count in tf.items()}


def _sparse_search(query: str, user_id: str, top_k: int) -> list[dict]:
    """
    Sparse keyword search using Qdrant's native sparse vector index.
    Falls back to [] gracefully if the sparse field doesn't exist yet
    (e.g. collections created before this update).
    """
    client = get_qdrant()

    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        return []

    try:
        info = client.get_collection(settings.qdrant_collection)
        sparse_configs = getattr(info.config.params, "sparse_vectors", None) or {}
        if SPARSE_FIELD not in sparse_configs:
            print(f"[Engram] Sparse field '{SPARSE_FIELD}' not found — "
                  f"falling back to vector-only search. "
                  f"Re-create the collection to enable sparse search.")
            return []
    except Exception as e:
        print(f"[Engram] Sparse field check failed (non-critical): {e}")
        return []

    tf_map = _tokenize(query)
    if not tf_map:
        return []

    sparse_vec = SparseVector(
        indices=list(tf_map.keys()),
        values=list(tf_map.values()),
    )

    try:
        results = client.search(
            collection_name=settings.qdrant_collection,
            query_vector=NamedSparseVector(name=SPARSE_FIELD, vector=sparse_vec),
            query_filter=Filter(must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="is_latest", match=MatchValue(value=True)),
                FieldCondition(key="is_valid",  match=MatchValue(value=True)),
            ]),
            limit=top_k,
            with_payload=True,
        )
    except Exception as e:
        print(f"[Engram] Sparse search failed (non-critical): {e}")
        return []

    return [
        {
            "id":           str(r.id),
            "content":      r.payload["content"],
            "tags":         r.payload.get("tags", []),
            "created_at":   r.payload.get("created_at", ""),
            "sparse_score": round(r.score, 4),
        }
        for r in results
    ]


# ── RRF merge ─────────────────────────────────────────────────────

def _rrf_merge(
    vector_results: list[dict],
    sparse_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion — merges two ranked lists.
    score = sum of 1/(k + rank) across both lists.
    k=60 is the standard RRF constant (Robertson et al.).

    Works correctly when either list is empty — the other list's
    scores dominate, giving graceful fallback behaviour.
    """
    scores:    dict[str, float] = {}
    all_items: dict[str, dict]  = {}

    for rank, item in enumerate(vector_results):
        mid = item["id"]
        scores[mid]    = scores.get(mid, 0.0) + 1.0 / (k + rank + 1)
        all_items[mid] = item

    for rank, item in enumerate(sparse_results):
        mid = item["id"]
        scores[mid]    = scores.get(mid, 0.0) + 1.0 / (k + rank + 1)
        all_items[mid] = item

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

    return [
        {**all_items[mid], "rrf_score": round(scores[mid], 6)}
        for mid in sorted_ids
    ]


# ── Public API ────────────────────────────────────────────────────

def hybrid_search(query: str, user_id: str = "default", top_k: int = None) -> list[dict]:
    """
    Full hybrid search pipeline.
    Dense vector + sparse keyword → RRF merge → top_k results.

    If sparse search is unavailable (old collection without the sparse
    field), falls back to vector-only results transparently.
    """
    if top_k is None:
        top_k = settings.top_k_retrieval

    vector_results = _vector_search(query, user_id, top_k)
    sparse_results = _sparse_search(query, user_id, top_k)
    merged         = _rrf_merge(vector_results, sparse_results)

    return merged[:top_k]
