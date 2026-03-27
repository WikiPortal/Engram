"""
Engram — FalkorDB Knowledge Graph

Stores typed relationships between memories with full temporal metadata.

Edge types:
  UPDATES    — new memory supersedes an existing one (job changed, moved city)
  EXTENDS    — new memory enriches an existing one (more detail added)
  DERIVES    — inferred connection (different topics, logically linked)
  SUPERSEDES — temporal override: new fact replaces old, with full history kept
               This is the immutable temporal edge — old state is NEVER deleted,
               only marked as no longer the latest version.

"""

import json
from datetime import datetime, timezone
from falkordb import FalkorDB
from llm import complete
from config import get_settings

settings = get_settings()

GRAPH_NAME = "engram"

# ── Relationship types ────────────────────────────────────────────
UPDATES    = "UPDATES"    
EXTENDS    = "EXTENDS"    
DERIVES    = "DERIVES"    
SUPERSEDES = "SUPERSEDES" 

# ── LLM prompt ───────────────────────────────────────────────────
CLASSIFY_PROMPT = """You are a memory graph classifier for a personal AI memory system.

Given two memory facts, classify their relationship:

UPDATES  — new fact directly supersedes the old one. The old fact is now stale or wrong.
           Example: old="User works at Acrobat", new="User works at Google"
EXTENDS  — new fact adds detail to the old one. Both remain valid and useful together.
           Example: old="User likes coffee", new="User prefers dark roast espresso"
DERIVES  — the two facts are related but neither supersedes the other.
           Example: old="User has a dog", new="User walks 5km every morning"
NONE     — the facts are unrelated. Do not create a spurious edge.

Return ONLY valid JSON, no markdown:
{
  "relationship": "UPDATES" | "EXTENDS" | "DERIVES" | "NONE",
  "confidence": 0.0-1.0,
  "reason": "one sentence explanation"
}"""


# ── Client ───────────────────────────────────────────────────────

def _get_graph():
    """Connect to FalkorDB and return the engram graph handle."""
    db = FalkorDB(host=settings.falkordb_host, port=settings.falkordb_port)
    return db.select_graph(GRAPH_NAME)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Node operations ───────────────────────────────────────────────

def ensure_node(memory_id: str, user_id: str = "default", tcommit: str = None) -> bool:
    """
    Create a Memory node if it doesn't already exist.
    Stores tcommit (ingestion timestamp) on creation.
    MERGE is idempotent — safe to call repeatedly.
    """
    try:
        g = _get_graph()
        g.query(
            "MERGE (m:Memory {id: $id}) "
            "ON CREATE SET m.user_id = $user_id, m.tcommit = $tcommit",
            {
                "id":      memory_id,
                "user_id": user_id,
                "tcommit": tcommit or _now_iso(),
            }
        )
        return True
    except Exception as e:
        print(f"[Engram:Graph] ensure_node failed: {e}")
        return False


# ── Relationship classification ───────────────────────────────────

def _classify_relationship(old_content: str, new_content: str) -> dict:
    """
    Ask the LLM to classify the relationship between two memory facts.
    Returns dict with relationship, confidence, reason.
    Falls back to NONE on any failure.
    """
    try:
        raw = complete(
            system=CLASSIFY_PROMPT,
            user=f"Old memory: {old_content}\n\nNew memory: {new_content}"
        )
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return {
            "relationship": data.get("relationship", "NONE"),
            "confidence":   float(data.get("confidence", 0.0)),
            "reason":       data.get("reason", ""),
        }
    except Exception as e:
        print(f"[Engram:Graph] Classification failed: {e}")
        return {"relationship": "NONE", "confidence": 0.0, "reason": str(e)}


# ── Community detection (cycle guard) ────────────────────────────

def _would_create_cycle(from_id: str, to_id: str) -> bool:
    """Check if adding from_id → to_id would create a cycle."""
    try:
        g = _get_graph()
        result = g.ro_query(
            "MATCH p = (start:Memory {id: $to_id})-[*1..5]->(end:Memory {id: $from_id}) "
            "RETURN count(p) AS cnt",
            {"to_id": to_id, "from_id": from_id}
        )
        if result.result_set and result.result_set[0][0] > 0:
            return True
    except Exception as e:
        print(f"[Engram:Graph] Cycle check failed (allowing edge): {e}")
    return False


def _community_check_passed(from_id: str, to_id: str, user_id: str) -> bool:
    """Guard: no cycle, both nodes belong to the same user."""
    if _would_create_cycle(from_id, to_id):
        print(f"[Engram:Graph] Cycle detected — skipping {from_id[:8]} → {to_id[:8]}")
        return False
    try:
        g = _get_graph()
        result = g.ro_query(
            "MATCH (a:Memory {id: $from_id}), (b:Memory {id: $to_id}) "
            "WHERE a.user_id = $user_id AND b.user_id = $user_id "
            "RETURN count(*) AS cnt",
            {"from_id": from_id, "to_id": to_id, "user_id": user_id}
        )
        if not result.result_set or result.result_set[0][0] == 0:
            return False
    except Exception as e:
        print(f"[Engram:Graph] Community check failed (blocking edge): {e}")
        return False
    return True


# ── Edge creation ─────────────────────────────────────────────────

def _create_edge(from_id: str, to_id: str, rel_type: str, confidence: float, reason: str):
    """Create a directed typed relationship."""
    g = _get_graph()
    g.query(
        f"MATCH (a:Memory {{id: $from_id}}), (b:Memory {{id: $to_id}}) "
        f"MERGE (a)-[r:{rel_type}]->(b) "
        f"ON CREATE SET r.confidence = $confidence, r.reason = $reason, r.tcommit = $tcommit",
        {
            "from_id":    from_id,
            "to_id":      to_id,
            "confidence": confidence,
            "reason":     reason,
            "tcommit":    _now_iso(),
        }
    )
    print(
        f"[Engram:Graph] Edge [{rel_type}] {from_id[:8]} → {to_id[:8]} "
        f"(conf={confidence:.2f}): {reason[:60]}"
    )


# ── Temporal supersession ─────────────────────────────────────────

def record_supersession(
    old_memory_id:  str,
    new_memory_id:  str,
    old_content:    str,
    new_content:    str,
    reason:         str,
    user_id:        str = "default",
) -> bool:
    """
    Record that new_memory_id supersedes old_memory_id in the temporal graph.

    This is the core of the immutable temporal design:
      - Creates/ensures both Memory nodes with tcommit timestamps
      - Creates a SUPERSEDES edge from old → new carrying:
          tcommit     — when this supersession was recorded
          reason      — why the old fact was replaced
          old_content — snapshot of the old state (for history queries)
          new_content — snapshot of the new state

    The old memory is NOT deleted from Qdrant here — contradiction.py
    handles the Qdrant payload update (is_latest=False, is_valid=False).
    This function only handles the graph layer.

    With this in place, queries like "where did I live in 2023?" become
    answerable by traversing SUPERSEDES edges and checking tcommit.

    Returns True if the edge was created, False on any failure.
    """
    try:
        now = _now_iso()
        g   = _get_graph()

        ensure_node(old_memory_id, user_id, tcommit=now)
        ensure_node(new_memory_id, user_id, tcommit=now)

        g.query(
            "MATCH (old:Memory {id: $old_id}), (new:Memory {id: $new_id}) "
            "MERGE (old)-[r:SUPERSEDES]->(new) "
            "ON CREATE SET "
            "  r.tcommit     = $tcommit, "
            "  r.reason      = $reason, "
            "  r.old_content = $old_content, "
            "  r.new_content = $new_content",
            {
                "old_id":      old_memory_id,
                "new_id":      new_memory_id,
                "tcommit":     now,
                "reason":      reason,
                "old_content": old_content[:500],  # cap to avoid huge graph properties
                "new_content": new_content[:500],
            }
        )
        print(
            f"[Engram:Graph] SUPERSEDES {old_memory_id[:8]} → {new_memory_id[:8]}: "
            f"{reason[:80]}"
        )
        return True

    except Exception as e:
        print(f"[Engram:Graph] record_supersession failed (non-critical): {e}")
        return False


# ── Temporal query API ────────────────────────────────────────────

def get_history(memory_id: str, user_id: str = "default") -> list[dict]:
    """
    Traverse SUPERSEDES edges to return the full temporal history
    for the chain containing memory_id.

    Walks backwards (what did this supersede?) and forwards (what
    superseded this?) to reconstruct the complete state timeline.

    Returns list of dicts ordered oldest → newest:
      {
        "id":          memory_id,
        "tcommit":     ISO timestamp when this version was ingested,
        "superseded_by": memory_id or None,
        "supersedes":    memory_id or None,
        "reason":      why this version replaced the previous,
        "old_content": what the previous state said,
      }
    """
    try:
        g = _get_graph()

        # Walk the full SUPERSEDES chain in both directions
        result = g.ro_query(
            "MATCH path = (oldest:Memory)-[:SUPERSEDES*0..20]->(m:Memory {id: $id}) "
            "WHERE oldest.user_id = $user_id "
            "WITH oldest ORDER BY oldest.tcommit ASC LIMIT 1 "
            "MATCH chain = (oldest)-[:SUPERSEDES*0..20]->(each:Memory) "
            "WHERE each.user_id = $user_id "
            "OPTIONAL MATCH (each)-[r_fwd:SUPERSEDES]->(next:Memory) "
            "OPTIONAL MATCH (prev:Memory)-[r_bwd:SUPERSEDES]->(each) "
            "RETURN each.id, each.tcommit, "
            "       next.id, r_fwd.reason, r_fwd.old_content, "
            "       prev.id "
            "ORDER BY each.tcommit ASC",
            {"id": memory_id, "user_id": user_id}
        )

        history = []
        for row in result.result_set:
            history.append({
                "id":            row[0],
                "tcommit":       row[1],
                "superseded_by": row[2],
                "reason":        row[3],
                "old_content":   row[4],
                "supersedes":    row[5],
            })
        return history

    except Exception as e:
        print(f"[Engram:Graph] get_history failed: {e}")
        return []


def get_supersession_chain(memory_id: str, user_id: str = "default") -> list[dict]:
    """
    Simpler version: just return the direct SUPERSEDES neighbours
    (one hop back, one hop forward) for a given memory.
    Used by the API to show "this replaced X / was replaced by Y".
    """
    try:
        g = _get_graph()
        result = g.ro_query(
            "MATCH (m:Memory {id: $id}) "
            "OPTIONAL MATCH (m)-[fwd:SUPERSEDES]->(newer:Memory {user_id: $uid}) "
            "OPTIONAL MATCH (older:Memory {user_id: $uid})-[bwd:SUPERSEDES]->(m) "
            "RETURN "
            "  older.id, bwd.reason, bwd.tcommit, bwd.old_content, "
            "  newer.id, fwd.reason, fwd.tcommit",
            {"id": memory_id, "uid": user_id}
        )

        if not result.result_set:
            return []

        row = result.result_set[0]
        chain = []
        if row[0]:  # has a predecessor
            chain.append({
                "direction":   "supersedes",
                "memory_id":   row[0],
                "reason":      row[1],
                "tcommit":     row[2],
                "old_content": row[3],
            })
        if row[4]:  # has a successor
            chain.append({
                "direction": "superseded_by",
                "memory_id": row[4],
                "reason":    row[5],
                "tcommit":   row[6],
            })
        return chain

    except Exception as e:
        print(f"[Engram:Graph] get_supersession_chain failed: {e}")
        return []


# ── Public API ────────────────────────────────────────────────────

def link_memories(
    new_memory_id:    str,
    new_content:      str,
    candidate_memories: list,
    user_id:          str = "default",
) -> list:
    """
    Main entry point. Called after a new memory is stored in Qdrant.

    For each candidate memory:
      1. Classify relationship via LLM
      2. Skip if NONE or confidence < graph_confidence_threshold
      3. Community detection guard (no cycles, same user)
      4. Create typed edge in FalkorDB with tcommit timestamp

    Returns list of edges created.
    """
    if not candidate_memories:
        return []

    now = _now_iso()
    ensure_node(new_memory_id, user_id, tcommit=now)
    edges_created = []

    for candidate in candidate_memories:
        old_id      = candidate["id"]
        old_content = candidate["content"]

        if old_id == new_memory_id:
            continue

        ensure_node(old_id, user_id, tcommit=now)

        result     = _classify_relationship(old_content, new_content)
        rel_type   = result["relationship"]
        confidence = result["confidence"]
        reason     = result["reason"]

        if rel_type == "NONE":
            continue

        if confidence < settings.graph_confidence_threshold:
            print(
                f"[Engram:Graph] Low confidence ({confidence:.2f}) — "
                f"skipping {rel_type} {old_id[:8]} → {new_memory_id[:8]}"
            )
            continue

        if not _community_check_passed(old_id, new_memory_id, user_id):
            continue

        try:
            _create_edge(old_id, new_memory_id, rel_type, confidence, reason)
            edges_created.append({
                "from":       old_id,
                "to":         new_memory_id,
                "type":       rel_type,
                "confidence": confidence,
                "reason":     reason,
            })
        except Exception as e:
            print(f"[Engram:Graph] Edge creation failed: {e}")

    return edges_created


def get_related(memory_id: str, user_id: str = "default", depth: int = 2) -> list:
    """
    Traverse the graph to find memories related to memory_id.
    Uses iterative single-hop queries to avoid FalkorDB variable-length
    path limitations.
    """
    try:
        g = _get_graph()
        seen     = {memory_id}
        results  = []
        frontier = [memory_id]

        for _ in range(depth):
            if not frontier:
                break
            params  = {"user_id": user_id}
            id_list = ", ".join(f"\"{mid}\"" for mid in frontier)
            result  = g.ro_query(
                f"MATCH (start:Memory)-[r]->(related:Memory) "
                f"WHERE start.id IN [{id_list}] "
                f"AND related.user_id = $user_id "
                f"RETURN related.id, type(r), r.confidence",
                params
            )
            next_frontier = []
            for row in result.result_set:
                rid, rel_type, confidence = row[0], row[1], row[2]
                if rid and rid not in seen:
                    seen.add(rid)
                    next_frontier.append(rid)
                    results.append({
                        "id":         rid,
                        "rel_type":   rel_type or "UNKNOWN",
                        "confidence": float(confidence) if confidence is not None else 0.0,
                    })
            frontier = next_frontier

        return sorted(results, key=lambda x: x["confidence"], reverse=True)[:10]

    except Exception as e:
        print(f"[Engram:Graph] get_related failed: {e}")
        return []


def invalidate_edges(memory_id: str):
    """
    When a memory is superseded, mark its outgoing UPDATES edges inactive.
    SUPERSEDES edges are permanent and never marked inactive — they form
    the immutable temporal record.
    """
    try:
        g = _get_graph()
        result = g.query(
            "MATCH (m:Memory {id: $id})-[r:UPDATES]->() "
            "SET r.active = false "
            "RETURN count(r) AS cnt",
            {"id": memory_id}
        )
        if result.result_set:
            count = result.result_set[0][0]
            if count:
                print(f"[Engram:Graph] Marked {count} UPDATES edge(s) inactive for {memory_id[:8]}")
    except Exception as e:
        print(f"[Engram:Graph] invalidate_edges failed (non-critical): {e}")


def get_graph_stats(user_id: str = "default") -> dict:
    """Node/edge counts per user. Used by health checks and dashboard."""
    stats = {"nodes": 0, "edges": 0, "updates": 0, "extends": 0, "derives": 0, "supersedes": 0}
    try:
        g = _get_graph()
        res = g.ro_query(
            "MATCH (m:Memory {user_id: $uid}) RETURN count(m)",
            {"uid": user_id}
        )
        if res.result_set:
            stats["nodes"] = res.result_set[0][0]

        for rel_type, key in [
            (UPDATES,    "updates"),
            (EXTENDS,    "extends"),
            (DERIVES,    "derives"),
            (SUPERSEDES, "supersedes"),
        ]:
            res = g.ro_query(
                f"MATCH (:Memory {{user_id: $uid}})-[r:{rel_type}]->() RETURN count(r)",
                {"uid": user_id}
            )
            if res.result_set:
                stats[key]    = res.result_set[0][0]
                stats["edges"] += stats[key]
    except Exception as e:
        print(f"[Engram:Graph] get_graph_stats failed: {e}")
    return stats
