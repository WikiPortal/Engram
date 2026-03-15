"""
Engram — Full Pipeline Test
Run from project root: python tests/test_brain.py
This is the end-to-end test of the entire backend.
"""
import sys
sys.path.append("backend")

from brain import remember, recall, chat

USER = "test_brain"


def test_remember():
    print("  Testing remember() — full store pipeline...")
    result = remember(
        "Had a team meeting today. John leads backend. We agreed the API uses camelCase. Deadline is next Friday.",
        user_id=USER,
        tags=["meeting"]
    )
    print(f"  Stored: {result['stored']} facts")
    print(f"  Skipped duplicates: {result['skipped_duplicates']}")
    print(f"  Contradictions resolved: {result['contradictions_resolved']}")
    for f in result["facts"]:
        print(f"    → {f[:70]}")
    assert result["stored"] > 0, "Should store at least 1 fact"
    print("  ✅ remember() working")


def test_recall():
    print("\n  Testing recall() — full retrieval pipeline...")
    result = recall("what naming convention do we use for APIs?", user_id=USER)
    print(f"  Found {result['total_found']} candidates → top {len(result['memories'])} after rerank")
    print(f"  Context tokens: {result['context_tokens']}")
    for m in result["memories"]:
        print(f"    [{m.get('rerank_score', '?')}] {m['content'][:65]}")
    assert len(result["memories"]) > 0, "Should recall at least 1 memory"
    print("  ✅ recall() working")


def test_chat():
    print("\n  Testing chat() — memory-augmented response...")
    response = chat("What naming convention did we agree on for APIs?", user_id=USER)
    print(f"  Response: {response[:150]}")
    assert len(response) > 0, "Should return a response"
    assert "camelCase" in response or "camel" in response.lower(), \
        f"Response should mention camelCase, got: {response}"
    print("  ✅ chat() working — memory injected correctly")


if __name__ == "__main__":
    print("\n🧠 Engram — Full Pipeline Test\n")
    try:
        test_remember()
        test_recall()
        test_chat()
        print()
        print("✅ Full pipeline working.\n")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)
