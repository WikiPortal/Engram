"""
Engram — Hybrid Search (Step 11)
Combines BM25 keyword search + vector similarity search.
Merges results via Reciprocal Rank Fusion (RRF).
Semantic drift — pure vector misses exact terms.
"""
from db import get_qdrant
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from rank_bm25 import BM25Okapi
from embedder import embedder
from config import get_settings

settings = get_settings()


def _get_all_memories(user_id: str) -> list[dict]:
    """Fetch all valid memories for BM25 corpus."""
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
        limit=1000,
        with_payload=True,
        with_vectors=False
    )

    return [
        {
            "id": str(r.id),
            "content": r.payload["content"],
            "tags": r.payload.get("tags", []),
            "created_at": r.payload.get("created_at", ""),
        }
        for r in results
    ]


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
            FieldCondition(key="is_valid", match=MatchValue(value=True)),
        ]),
        limit=top_k,
        with_payload=True
    )

    return [
        {
            "id": str(r.id),
            "content": r.payload["content"],
            "tags": r.payload.get("tags", []),
            "created_at": r.payload.get("created_at", ""),
            "vector_score": round(r.score, 4),
        }
        for r in results
    ]


def _bm25_search(query: str, all_memories: list[dict], top_k: int) -> list[dict]:
    """Sparse BM25 keyword search over all memories."""
    if not all_memories:
        return []

    corpus = [m["content"] for m in all_memories]
    tokenized = [doc.lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())

    scored = sorted(
        [(scores[i], all_memories[i]) for i in range(len(all_memories))],
        key=lambda x: x[0],
        reverse=True
    )

    return [
        {**item, "bm25_score": round(float(score), 4)}
        for score, item in scored[:top_k]
        if score > 0
    ]


def _rrf_merge(vector_results: list[dict], bm25_results: list[dict], k: int = 60) -> list[dict]:
    """
    Reciprocal Rank Fusion — merges two ranked lists.
    score = sum of 1/(k + rank) across both lists.
    k=60 is the standard RRF constant.
    """
    scores = {}
    all_items = {}

    for rank, item in enumerate(vector_results):
        mid = item["id"]
        scores[mid] = scores.get(mid, 0) + 1 / (k + rank + 1)
        all_items[mid] = item

    for rank, item in enumerate(bm25_results):
        mid = item["id"]
        scores[mid] = scores.get(mid, 0) + 1 / (k + rank + 1)
        all_items[mid] = item

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)

    return [
        {**all_items[mid], "rrf_score": round(scores[mid], 6)}
        for mid in sorted_ids
    ]


def hybrid_search(query: str, user_id: str = "default", top_k: int = None) -> list[dict]:
    """
    Full hybrid search pipeline.
    BM25 + Vector → RRF merge → top_k results.
    """
    if top_k is None:
        top_k = settings.top_k_retrieval

    all_memories = _get_all_memories(user_id)
    vector_results = _vector_search(query, user_id, top_k)
    bm25_results = _bm25_search(query, all_memories, top_k)
    merged = _rrf_merge(vector_results, bm25_results)

    return merged[:top_k]
