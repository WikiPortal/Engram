"""
Engram — Contradiction Resolution (Step 9)
When new fact contradicts existing memory:
  1. Find the conflicting memory in Qdrant
  2. Mark it is_latest=False, is_valid=False
  3. Log it in PostgreSQL audit trail
  4. New fact gets stored as the authoritative version
stale/conflicting facts poisoning recall results.
"""
from db import get_pg, get_qdrant
from datetime import datetime
from qdrant_client.models import Filter, FieldCondition, MatchValue
from embedder import embedder
from config import get_settings

settings = get_settings()


def _pg_conn():
    return get_pg()


def invalidate_memory(memory_id: str, reason: str = ""):
    """
    Mark a memory as no longer valid in Qdrant.
    Logs the action in PostgreSQL audit_log.
    """
    client = get_qdrant()

    # Mark invalid in Qdrant
    client.set_payload(
        collection_name=settings.qdrant_collection,
        payload={
            "is_latest": False,
            "is_valid": False,
            "invalid_at": datetime.utcnow().isoformat()
        },
        points=[memory_id]
    )

    # Log to PostgreSQL audit trail
    try:
        conn = _pg_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO audit_log (memory_id, action, reason)
               VALUES (%s, %s, %s)""",
            (memory_id, "INVALIDATED", reason)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[Engram] Audit log failed (non-critical): {e}")

    print(f"[Engram] Invalidated [{memory_id[:8]}]: {reason}")


def find_conflicting(new_content: str, user_id: str = "default") -> list[dict]:
    """
    Find existing memories that are semantically close to the new fact.
    These are candidates for contradiction checking.
    Returns top 5 similar valid memories.
    """
    client = get_qdrant()

    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        return []

    vector = embedder.embed(new_content)

    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        query_filter=Filter(must=[
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            FieldCondition(key="is_latest", match=MatchValue(value=True)),
            FieldCondition(key="is_valid", match=MatchValue(value=True)),
        ]),
        limit=5,
        with_payload=True
    )

    return [
        {
            "id": str(r.id),
            "content": r.payload["content"],
            "score": round(r.score, 4)
        }
        for r in results
        if r.score > 0.5  # only semantically related memories worth checking
    ]


def resolve(new_content: str, user_id: str = "default") -> tuple[bool, list[str]]:
    """
    Full contradiction resolution pipeline.
    1. Find semantically similar existing memories (candidates)
    2. Check each candidate individually against the new fact
    3. Invalidate only the ones the LLM explicitly flags as contradicting

    Key fix over the old approach: the old code called is_contradiction()
    on the entire candidate list as a batch, then invalidated ALL of them
    the moment any contradiction was detected. This caused false-positive
    deletions of unrelated but semantically nearby memories.

    Now each candidate is checked in isolation — only exact contradictions
    are invalidated.

    Returns (any_contradiction_found, list_of_invalidated_ids)
    """
    from extractor import check_contradiction

    candidates = find_conflicting(new_content, user_id)
    if not candidates:
        return False, []

    invalidated = []

    for candidate in candidates:
        contradicts, reason = check_contradiction(new_content, candidate["content"])
        if contradicts:
            invalidate_memory(candidate["id"], reason=reason)
            invalidated.append(candidate["id"])
            print(
                f"[Engram] Contradiction resolved: [{candidate['id'][:8]}] "
                f"superseded by new fact. Reason: {reason}"
            )

    return len(invalidated) > 0, invalidated
