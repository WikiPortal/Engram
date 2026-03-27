"""
Engram — Contradiction Resolution

When a new fact contradicts an existing memory:
  1. Find semantically similar candidates in Qdrant
  2. Check each one individually with the LLM (per-fact, not batch)
  3. For each genuine contradiction:
       a. Mark old memory as superseded in Qdrant (is_latest=False, is_valid=False)
       b. Record a SUPERSEDES edge in FalkorDB with full temporal metadata
       c. Log the action in the PostgreSQL audit trail

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
    Mark a memory as superseded in Qdrant.
    Logs the action in the PostgreSQL audit trail.

    The memory is NOT deleted — it is only excluded from future searches
    by setting is_latest=False and is_valid=False. The graph layer
    (record_supersession) preserves the temporal history.
    """
    client = get_qdrant()

    client.set_payload(
        collection_name=settings.qdrant_collection,
        payload={
            "is_latest":   False,
            "is_valid":    False,
            "invalid_at":  datetime.utcnow().isoformat(),
            "superseded_reason": reason,
        },
        points=[memory_id]
    )

    try:
        conn = _pg_conn()
        cur  = conn.cursor()
        cur.execute(
            """INSERT INTO audit_log (memory_id, action, reason)
               VALUES (%s, %s, %s)""",
            (memory_id, "SUPERSEDED", reason)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[Engram] Audit log failed (non-critical): {e}")

    print(f"[Engram] Superseded [{memory_id[:8]}]: {reason}")


def find_conflicting(new_content: str, user_id: str = "default") -> list[dict]:
    """
    Find existing memories that are semantically close to the new fact.
    Returns top 5 similar valid memories as contradiction candidates.
    """
    client = get_qdrant()

    existing = [c.name for c in client.get_collections().collections]
    if settings.qdrant_collection not in existing:
        return []

    vector  = embedder.embed(new_content)
    results = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        query_filter=Filter(must=[
            FieldCondition(key="user_id", match=MatchValue(value=user_id)),
            FieldCondition(key="is_latest", match=MatchValue(value=True)),
            FieldCondition(key="is_valid",  match=MatchValue(value=True)),
        ]),
        limit=5,
        with_payload=True,
    )

    return [
        {
            "id":      str(r.id),
            "content": r.payload["content"],
            "score":   round(r.score, 4),
        }
        for r in results
        if r.score > 0.5
    ]


def resolve(
    new_content:   str,
    user_id:       str = "default",
    new_memory_id: str = None,
) -> tuple[bool, list[str]]:
    """
    Full contradiction resolution pipeline.

    1. Find semantically similar existing memories
    2. Check each candidate individually with the LLM
    3. For each confirmed contradiction:
         - Mark the old memory as superseded in Qdrant
         - Record a SUPERSEDES edge in the temporal graph
         - Log in audit trail

    Args:
        new_content:   The new fact being stored.
        user_id:       User namespace.
        new_memory_id: The Qdrant ID of the new memory (needed to create
                       the SUPERSEDES graph edge). If not provided, the
                       graph edge is skipped but Qdrant invalidation still runs.

    Returns:
        (any_contradiction_found, list_of_superseded_ids)
    """
    from extractor import check_contradiction
    from graph import record_supersession, invalidate_edges

    candidates = find_conflicting(new_content, user_id)
    if not candidates:
        return False, []

    superseded = []

    for candidate in candidates:
        contradicts, reason = check_contradiction(new_content, candidate["content"])
        if not contradicts:
            continue

        old_id      = candidate["id"]
        old_content = candidate["content"]

        invalidate_memory(old_id, reason=reason)
        superseded.append(old_id)

        if new_memory_id:
            record_supersession(
                old_memory_id=old_id,
                new_memory_id=new_memory_id,
                old_content=old_content,
                new_content=new_content,
                reason=reason,
                user_id=user_id,
            )

        invalidate_edges(old_id)

        print(
            f"[Engram] Contradiction resolved: [{old_id[:8]}] "
            f"superseded. Reason: {reason}"
        )

    return len(superseded) > 0, superseded
