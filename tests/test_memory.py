"""
Engram — Memory Store & Recall Test
Run from project root: python tests/test_memory.py
"""
import sys
sys.path.append("backend")

from memory import store, recall


def test_store_and_recall():

    print("  Storing 4 memories...")
    store("Team decided API responses should use camelCase", tags=["api", "backend"])
    store("John leads the backend team", tags=["team"])
    store("We use PostgreSQL as our main database", tags=["infra"])
    store("Deployment happens every Friday at 6pm", tags=["process"])
    print("  ✅ Stored 4 memories")

    print("  Recalling: 'API format decision'...")
    results = recall("API format decision")
    assert len(results) > 0, "Should return at least 1 result"
    top = results[0]
    assert "camelCase" in top["content"], f"Expected camelCase result, got: {top['content']}"
    print(f"  ✅ Top result (score {top['score']}): {top['content']}")

    print("  Recalling: 'who leads backend'...")
    results = recall("who leads backend")
    assert len(results) > 0
    print(f"  ✅ Top result (score {results[0]['score']}): {results[0]['content']}")

    print("  Recalling: 'database we use'...")
    results = recall("database we use")
    assert len(results) > 0
    print(f"  ✅ Top result (score {results[0]['score']}): {results[0]['content']}")


if __name__ == "__main__":
    print("\n🧠 Engram — Memory Store & Recall Test\n")
    try:
        test_store_and_recall()
        print()
        print("✅ Memory store + recall working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)