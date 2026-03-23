"""
Engram — Duplicate Detection (Step 8)
Before storing a fact, check if semantically identical memory exists.
Threshold: 0.92 cosine similarity → considered duplicate, skip storage.
Edge case handled: bloated memory store from redundant facts.
"""
from db import get_qdrant
from qdrant_client.models import Filter, FieldCondition, MatchValue
from embedder import embedder
from config import get_settings

settings = get_settings()


def is_duplicate(content: str, user_id: str = "default") -> tuple[bool, str, float]:
    """
    Check if a semantically identical memory already exists.
    Returns (is_dup, matching_content, similarity_score)
    Returns (False, "", 0.0) if no duplicate found.
    """
    client = get_qdrant()

    # Check collection exists
    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        return False, "", 0.0

    vector = embedder.embed(content)

    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        query_filter=Filter(must=[
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            FieldCondition(key="is_latest", match=MatchValue(value=True)),
            FieldCondition(key="is_valid", match=MatchValue(value=True)),
        ]),
        limit=1,
        with_payload=True
    )

    if not results:
        return False, "", 0.0

    top = results[0]
    score = round(top.score, 4)

    if score >= settings.duplicate_threshold:
        return True, top.payload["content"], score

    return False, "", score
