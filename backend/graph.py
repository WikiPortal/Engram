"""
Engram — FalkorDB Knowledge Graph (Step 14)

Stores typed relationships between memories:
  UPDATES  — new memory supersedes an existing one (e.g. job changed)
  EXTENDS  — new memory enriches an existing one (more detail added)
  DERIVES  — inferred connection between two related memories

Design decisions (from research paper):
  - Edges only created when LLM confidence > 0.85 (graph_confidence_threshold)
  - Community detection check before edge creation to prevent hallucinated edges
  - Never deletes nodes — mirrors the Qdrant "never delete" philosophy
  - Nodes store memory_id + user_id; full content lives in Qdrant

Usage:
  FalkorDB() connects to host:port from config (default localhost:6380).
  All public functions are non-blocking on failure — graph errors never
  break the core remember/recall pipeline.
"""

import json
from falkordb import FalkorDB
from llm import complete
from config import get_settings

settings = get_settings()

GRAPH_NAME = "engram"

# ── Relationship types ────────────────────────────────────────────
UPDATES = "UPDATES"   # new fact supersedes old (job changed, preference changed)
EXTENDS = "EXTENDS"   # new fact adds detail to existing (same topic, more info)
DERIVES = "DERIVES"   # inferred connection (different topics, logically linked)

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


# ── Node operations ───────────────────────────────────────────────

def ensure_node(memory_id: str, user_id: str = "default") -> bool:
    """
    Create a Memory node if it doesn't already exist.
    MERGE is idempotent — safe to call repeatedly.
    """
    try:
        g = _get_graph()
        g.query(
            "MERGE (m:Memory {id: $id}) "
            "ON CREATE SET m.user_id = $user_id",
            {"id": memory_id, "user_id": user_id}
        )
        return True
    except Exception as e:
        print(f"[Engram:Graph] ensure_node failed: {e}")
        return False


# ── Relationship classification ───────────────────────────────────

def _classify_relationship(old_content: str, new_content: str) -> dict:
    """
    Ask the configured LLM to classify the relationship between two memory facts.
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
            "confidence": float(data.get("confidence", 0.0)),
            "reason": data.get("reason", ""),
        }
    except Exception as e:
        print(f"[Engram:Graph] Classification failed: {e}")
        return {"relationship": "NONE", "confidence": 0.0, "reason": str(e)}


# ── Community detection (cycle guard) ────────────────────────────

def _would_create_cycle(from_id: str, to_id: str) -> bool:
    """
    Check if adding from_id → to_id would create a cycle.
    A cycle exists if to_id can already reach from_id through existing edges.
    """
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
    """
    Guard before edge creation:
      1. No cycle would be created
      2. Both nodes belong to the same user
    """
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
            print(f"[Engram:Graph] User mismatch or missing nodes — skipping edge")
            return False
    except Exception as e:
        print(f"[Engram:Graph] Community check failed (blocking edge): {e}")
        return False
    return True


# ── Edge creation ─────────────────────────────────────────────────

def _create_edge(from_id: str, to_id: str, rel_type: str, confidence: float, reason: str):
    """Create a directed typed relationship. Only called after community_check_passed()."""
    g = _get_graph()
    g.query(
        f"MATCH (a:Memory {{id: $from_id}}), (b:Memory {{id: $to_id}}) "
        f"MERGE (a)-[r:{rel_type}]->(b) "
        f"ON CREATE SET r.confidence = $confidence, r.reason = $reason",
        {"from_id": from_id, "to_id": to_id, "confidence": confidence, "reason": reason}
    )
    print(
        f"[Engram:Graph] Edge [{rel_type}] {from_id[:8]} → {to_id[:8]} "
        f"(conf={confidence:.2f}): {reason[:60]}"
    )


# ── Public API ────────────────────────────────────────────────────

def link_memories(
    new_memory_id: str,
    new_content: str,
    candidate_memories: list,
    user_id: str = "default",
) -> list:
    """
    Main entry point. Called after a new memory is stored in Qdrant.

    For each candidate memory:
      1. Classify relationship via Gemini
      2. Skip if NONE or confidence < graph_confidence_threshold (0.85)
      3. Community detection guard
      4. Create typed edge in FalkorDB

    Returns list of edges created.
    """
    if not candidate_memories:
        return []

    ensure_node(new_memory_id, user_id)
    edges_created = []

    for candidate in candidate_memories:
        old_id = candidate["id"]
        old_content = candidate["content"]

        if old_id == new_memory_id:
            continue

        ensure_node(old_id, user_id)

        # Step 1 — Classify
        result = _classify_relationship(old_content, new_content)
        rel_type = result["relationship"]
        confidence = result["confidence"]
        reason = result["reason"]

        if rel_type == "NONE":
            continue

        # Step 2 — Confidence gate
        if confidence < settings.graph_confidence_threshold:
            print(
                f"[Engram:Graph] Low confidence ({confidence:.2f}) — "
                f"skipping {rel_type} {old_id[:8]} → {new_memory_id[:8]}"
            )
            continue

        # Step 3 — Community detection
        if not _community_check_passed(old_id, new_memory_id, user_id):
            continue

        # Step 4 — Create edge
        try:
            _create_edge(old_id, new_memory_id, rel_type, confidence, reason)
            edges_created.append({
                "from": old_id,
                "to": new_memory_id,
                "type": rel_type,
                "confidence": confidence,
                "reason": reason,
            })
        except Exception as e:
            print(f"[Engram:Graph] Edge creation failed: {e}")

    return edges_created


def get_related(memory_id: str, user_id: str = "default", depth: int = 2) -> list:
    """
    Traverse the graph to find memories related to memory_id.
    Uses iterative single-hop queries to avoid FalkorDB's variable-length path
    limitation where last(r) on a path raises a type mismatch error.
    """
    try:
        g = _get_graph()
        seen = {memory_id}
        results = []
        frontier = [memory_id]

        for _ in range(depth):
            if not frontier:
                break
            # Query one hop out from all nodes in the current frontier
            params = {"user_id": user_id}
            id_list = ", ".join(f"\"{mid}\"" for mid in frontier)
            result = g.ro_query(
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
                        "id": rid,
                        "rel_type": rel_type or "UNKNOWN",
                        "confidence": float(confidence) if confidence is not None else 0.0,
                    })
            frontier = next_frontier

        return sorted(results, key=lambda x: x["confidence"], reverse=True)[:10]

    except Exception as e:
        print(f"[Engram:Graph] get_related failed: {e}")
        return []


def invalidate_edges(memory_id: str):
    """
    When a memory is invalidated (contradiction), mark its outgoing UPDATES
    edges inactive. Consistent with the no-delete policy.
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
    stats = {"nodes": 0, "edges": 0, "updates": 0, "extends": 0, "derives": 0}
    try:
        g = _get_graph()
        res = g.ro_query(
            "MATCH (m:Memory {user_id: $uid}) RETURN count(m)",
            {"uid": user_id}
        )
        if res.result_set:
            stats["nodes"] = res.result_set[0][0]

        for rel_type, key in [(UPDATES, "updates"), (EXTENDS, "extends"), (DERIVES, "derives")]:
            res = g.ro_query(
                f"MATCH (:Memory {{user_id: $uid}})-[r:{rel_type}]->() RETURN count(r)",
                {"uid": user_id}
            )
            if res.result_set:
                stats[key] = res.result_set[0][0]
                stats["edges"] += stats[key]
    except Exception as e:
        print(f"[Engram:Graph] get_graph_stats failed: {e}")
    return stats
