"""
Engram — Contradiction Resolution Test
Run from project root: python tests/test_contradiction.py
"""
import sys
sys.path.append("backend")

from memory import store, recall
from contradiction import resolve, find_conflicting

USER = "test_contradiction"


def test_contradiction_resolution():

    print("  Storing original fact...")
    store("John leads the backend team", user_id=USER, tags=["team"])
    print("  ✅ Stored: 'John leads the backend team'")

    print("\n  Verifying original is recalled...")
    results = recall("who leads backend", user_id=USER)
    assert any("John" in r["content"] for r in results), "John should be in recall"
    print(f"  ✅ Recalled: '{results[0]['content']}'")

    print("\n  Resolving contradiction: Sarah now leads backend...")
    found, invalidated = resolve("Sarah now leads the backend team", user_id=USER)
    assert found, "Should detect contradiction"
    assert len(invalidated) > 0, "Should invalidate old memory"
    print(f"  ✅ Contradiction found — invalidated {len(invalidated)} memory(s)")

    print("\n  Storing new authoritative fact...")
    store("Sarah now leads the backend team", user_id=USER, tags=["team"])

    print("\n  Verifying old fact no longer recalled...")
    results = recall("who leads backend", user_id=USER)
    john_still_there = any("John leads" in r["content"] for r in results)
    assert not john_still_there, f"John's old fact should be invalidated, but got: {[r['content'] for r in results]}"
    print(f"  ✅ Old fact gone — top result: '{results[0]['content']}'")


def test_no_false_positives():
    print("\n  Testing no false positives...")
    store("We use PostgreSQL as our database", user_id=USER)
    found, _ = resolve("Deployment happens every Friday", user_id=USER)
    assert not found, "Unrelated fact should not trigger contradiction"
    print("  ✅ Unrelated fact — no false contradiction")


if __name__ == "__main__":
    print("\n🧠 Engram — Contradiction Resolution Test\n")
    try:
        test_contradiction_resolution()
        test_no_false_positives()
        print()
        print("✅ Contradiction resolution working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)
