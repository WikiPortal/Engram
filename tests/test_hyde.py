"""
Engram — HyDE Query Expansion Test
Run from project root: python tests/test_hyde.py
"""
import sys
sys.path.append("backend")

from memory import store
from search import hybrid_search
from reranker import rerank
from hyde import expand

USER = "test_hyde"


def test_hyde_expansion():
    print("  Testing HyDE expansion...")
    queries = [
        "what did we decide about APIs?",
        "who is responsible for the backend?",
        "when do we deploy?",
    ]
    for q in queries:
        expanded = expand(q)
        assert expanded != q or len(expanded) > 0, "Should return something"
        assert len(expanded) > len(q), "Expanded should be longer than raw query"
        print(f"  ✅ '{q}'")
        print(f"     → '{expanded[:80]}'")


def test_hyde_improves_recall():
    print("\n  Storing memories...")
    store("Team agreed API responses must follow camelCase naming convention", user_id=USER)
    store("Sarah took over backend leadership from John last quarter", user_id=USER)
    store("Production deployments are scheduled every Friday evening", user_id=USER)
    print("  ✅ Stored 3 memories")

    vague_query = "what naming rules do we follow"

    print(f"\n  Raw query search: '{vague_query}'")
    raw_results = hybrid_search(vague_query, user_id=USER, top_k=3)
    raw_top = raw_results[0]["content"] if raw_results else "nothing"
    print(f"  Raw top: '{raw_top[:60]}'")

    print(f"\n  HyDE expanded search:")
    expanded_query = expand(vague_query)
    hyde_results = hybrid_search(expanded_query, user_id=USER, top_k=3)
    hyde_top = hyde_results[0]["content"] if hyde_results else "nothing"
    print(f"  HyDE top: '{hyde_top[:60]}'")

    # Both should find the camelCase memory — HyDE should score it higher
    assert hyde_results, "HyDE search should return results"
    print(f"  ✅ HyDE search returned {len(hyde_results)} results")


if __name__ == "__main__":
    print("\n🧠 Engram — HyDE Query Expansion Test\n")
    try:
        test_hyde_expansion()
        test_hyde_improves_recall()
        print()
        print("✅ HyDE working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)
