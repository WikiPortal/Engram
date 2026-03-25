"""
Engram — Hybrid Search Test
Run from project root: python tests/test_search.py
"""
import sys
sys.path.append("backend")

from memory import store
from search import hybrid_search

USER = "test_search"


def test_hybrid_search():

    print("  Storing test memories...")
    store("Team decided API responses should use camelCase", user_id=USER, tags=["api"])
    store("John leads the backend team", user_id=USER, tags=["team"])
    store("We use PostgreSQL as our main database", user_id=USER, tags=["infra"])
    store("Deployment pipeline runs every Friday at 6pm", user_id=USER, tags=["process"])
    store("The frontend uses React with TypeScript", user_id=USER, tags=["frontend"])
    print("  ✅ Stored 5 memories")

    print("\n  Testing semantic query (vector strength)...")
    results = hybrid_search("what naming convention do we use", user_id=USER, top_k=3)
    assert len(results) > 0
    top = results[0]
    assert "camelCase" in top["content"], f"Expected camelCase, got: {top['content']}"
    print(f"  ✅ Semantic query — top: '{top['content'][:60]}' (rrf: {top['rrf_score']})")

    print("\n  Testing keyword query (sparse / BM42 strength)...")
    results = hybrid_search("PostgreSQL", user_id=USER, top_k=3)
    assert len(results) > 0
    assert "PostgreSQL" in results[0]["content"], f"Sparse search should find exact keyword, got: {results[0]['content']}"
    print(f"  ✅ Keyword query  — top: '{results[0]['content'][:60]}' (rrf: {results[0]['rrf_score']})")

    print("\n  Testing hybrid wins over pure vector...")
    results = hybrid_search("Friday deployment", user_id=USER, top_k=3)
    assert len(results) > 0
    print(f"  ✅ Hybrid query   — top: '{results[0]['content'][:60]}' (rrf: {results[0]['rrf_score']})")

    print("\n  Top 3 results with scores:")
    all_results = hybrid_search("backend team API", user_id=USER, top_k=3)
    for i, r in enumerate(all_results, 1):
        print(f"  {i}. [{r['rrf_score']}] {r['content'][:60]}")


if __name__ == "__main__":
    print("\n🧠 Engram — Hybrid Search Test\n")
    try:
        test_hybrid_search()
        print()
        print("✅ Hybrid search working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)
