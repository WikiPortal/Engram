"""
Engram — Duplicate Detection Test
Run from project root: python tests/test_dedup.py
"""
import sys
sys.path.append("backend")

from memory import store
from dedup import is_duplicate

USER = "test_dedup"


def test_dedup():
    print("  Storing original memory...")
    store("Team decided API responses should use camelCase", user_id=USER)

    print("  Testing exact duplicate...")
    dup, match, score = is_duplicate("Team decided API responses should use camelCase", user_id=USER)
    assert dup, f"Exact copy should be flagged as duplicate (score: {score})"
    print(f"  ✅ Exact duplicate caught    — score: {score}")

    print("  Testing near duplicate...")
    dup, match, score = is_duplicate("API responses must use camelCase format", user_id=USER)
    assert dup, f"Near duplicate should be flagged as score {score} is above 0.80 threshold"
    print(f"  ✅ Near duplicate caught     — score: {score} | matched: '{match[:50]}'")

    print("  Testing unrelated content...")
    dup, match, score = is_duplicate("I love hiking in the mountains on weekends", user_id=USER)
    assert not dup, f"Unrelated content should NOT be flagged (score: {score})"
    print(f"  ✅ Unrelated content ignored — score: {score}")


if __name__ == "__main__":
    print("\n🧠 Engram — Duplicate Detection Test\n")
    try:
        test_dedup()
        print()
        print("✅ Duplicate detection working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)