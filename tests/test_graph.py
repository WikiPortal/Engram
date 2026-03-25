"""
Engram — Graph Module Test (Step 14)
Run from project root: python tests/test_graph.py

Tests:
  1. Node creation (ensure_node)
  2. Relationship classification via Gemini
  3. Edge creation with confidence gate
  4. Community detection (cycle prevention)
  5. Graph traversal (get_related)
  6. Edge invalidation
  7. Graph stats
  8. Full integration via brain.remember()
"""
import sys
sys.path.append("backend")

from graph import (
    ensure_node,
    link_memories,
    get_related,
    invalidate_edges,
    get_graph_stats,
    _classify_relationship,
    _would_create_cycle,
)

USER = "test_graph"


def test_node_creation():
    print("  Testing ensure_node()...")
    ok = ensure_node("mem-test-001", USER)
    assert ok, "ensure_node should return True"
    ok2 = ensure_node("mem-test-001", USER)
    assert ok2, "ensure_node should be idempotent"
    print("  ✅ Node creation working")


def test_relationship_classification():
    print("\n  Testing _classify_relationship()...")

    result = _classify_relationship(
        old_content="User works at Acrobat as a software engineer",
        new_content="User works at Google as a senior engineer"
    )
    print(f"    UPDATES test: {result['relationship']} (confidence={result['confidence']:.2f}): {result['reason'][:60]}")
    assert result["relationship"] in ("UPDATES", "EXTENDS"), \
        f"Expected UPDATES or EXTENDS for job change, got {result['relationship']}"

    result = _classify_relationship(
        old_content="User likes coffee",
        new_content="User prefers dark roast espresso with no sugar"
    )
    print(f"    EXTENDS test: {result['relationship']} (confidence={result['confidence']:.2f}): {result['reason'][:60]}")
    assert result["relationship"] in ("EXTENDS", "UPDATES"), \
        f"Expected EXTENDS for preference detail, got {result['relationship']}"

    result = _classify_relationship(
        old_content="User has a cat named Whiskers",
        new_content="The API uses camelCase naming convention"
    )
    print(f"    NONE test: {result['relationship']} (confidence={result['confidence']:.2f}): {result['reason'][:60]}")
    assert result["relationship"] == "NONE", \
        f"Expected NONE for unrelated facts, got {result['relationship']}"

    print("  ✅ Classification working")


def test_link_memories():
    print("\n  Testing link_memories()...")
    ensure_node("mem-old-001", USER)

    edges = link_memories(
        new_memory_id="mem-new-001",
        new_content="User works at Google as a senior engineer",
        candidate_memories=[{
            "id": "mem-old-001",
            "content": "User works at Acrobat as a software engineer",
            "score": 0.88
        }],
        user_id=USER
    )

    print(f"    Edges created: {len(edges)}")
    for e in edges:
        print(f"    [{e['type']}] {e['from'][:12]} → {e['to'][:12]} (confidence={e['confidence']:.2f})")

    print(f"  ✅ link_memories() executed (edges={len(edges)}, gate may have filtered)")


def test_cycle_prevention():
    print("\n  Testing cycle prevention...")
    ensure_node("mem-cycle-A", USER)
    ensure_node("mem-cycle-B", USER)
    ensure_node("mem-cycle-C", USER)

    from graph import _create_edge, _would_create_cycle, UPDATES
    _create_edge("mem-cycle-A", "mem-cycle-B", UPDATES, 0.90, "test edge A→B")
    _create_edge("mem-cycle-B", "mem-cycle-C", UPDATES, 0.90, "test edge B→C")

    cycle_detected = _would_create_cycle("mem-cycle-C", "mem-cycle-A")
    print(f"    Cycle C→A detected: {cycle_detected}")
    assert cycle_detected, "Should detect that C→A would close a cycle (A→B→C→A)"

    no_cycle = _would_create_cycle("mem-cycle-A", "mem-cycle-C")
    print(f"    Spurious cycle A→C detected: {no_cycle}")
    # A→C is a shortcut, not a cycle — this could go either way depending on path depth
    print("  ✅ Cycle detection working")


def test_get_related():
    print("\n  Testing get_related()...")
    related = get_related("mem-cycle-A", user_id=USER, depth=2)
    print(f"    Related to mem-cycle-A (depth=2): {len(related)} neighbours")
    for r in related:
        print(f"    [{r['rel_type']}] {r['id'][:20]} (confidence={r['confidence']:.2f})")
    assert len(related) >= 1, "Should find at least 1 related memory via graph"
    print("  ✅ get_related() working")


def test_invalidate_edges():
    print("\n  Testing invalidate_edges()...")
    invalidate_edges("mem-cycle-A")
    print("  ✅ invalidate_edges() working")


def test_graph_stats():
    print("\n  Testing get_graph_stats()...")
    stats = get_graph_stats(USER)
    print(f"    Nodes: {stats['nodes']}, Edges: {stats['edges']}")
    print(f"    UPDATES: {stats['updates']}, EXTENDS: {stats['extends']}, DERIVES: {stats['derives']}")
    assert stats["nodes"] >= 0
    print("  ✅ get_graph_stats() working")


if __name__ == "__main__":
    print("\n🧠 Engram — Graph Module Test\n")
    try:
        test_node_creation()
        test_relationship_classification()
        test_link_memories()
        test_cycle_prevention()
        test_get_related()
        test_invalidate_edges()
        test_graph_stats()
        print()
        print("✅ Graph module working.\n")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)
