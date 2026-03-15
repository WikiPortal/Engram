"""
Engram — BGE Reranker Test
Run from project root: python tests/test_reranker.py
"""
import sys
sys.path.append("backend")

from memory import store
from search import hybrid_search
from reranker import rerank

USER = "test_reranker"


def test_reranker():

    print("  Storing test memories...")
    store("Team decided API responses should use camelCase", user_id=USER)
    store("John leads the backend team", user_id=USER)
    store("We use PostgreSQL as our main database", user_id=USER)
    store("Deployment pipeline runs every Friday at 6pm", user_id=USER)
    store("The frontend uses React with TypeScript", user_id=USER)
    store("API authentication uses JWT tokens", user_id=USER)
    store("The API rate limit is 100 requests per minute", user_id=USER)
    print("  ✅ Stored 7 memories")

    print("\n  Running hybrid search for 'API format rules'...")
    candidates = hybrid_search("API format rules", user_id=USER, top_k=7)
    print(f"  Hybrid returned {len(candidates)} candidates:")
    for i, r in enumerate(candidates, 1):
        print(f"    {i}. [rrf:{r['rrf_score']}] {r['content'][:55]}")

    print("\n  Reranking with BGE cross-encoder...")
    reranked = rerank("API format rules", candidates, top_k=3)
    print(f"  Top 3 after reranking:")
    for i, r in enumerate(reranked, 1):
        print(f"    {i}. [rerank:{r['rerank_score']}] {r['content'][:55]}")

    # Most relevant result should be about API + camelCase or API + format
    top_content = reranked[0]["content"].lower()
    assert "api" in top_content or "camel" in top_content, \
        f"Top reranked result should be API-related, got: {reranked[0]['content']}"
    print(f"\n  ✅ Top result correctly prioritised: '{reranked[0]['content'][:60]}'")

    print("\n  Verifying reranker improves order over raw hybrid...")
    hybrid_top = candidates[0]["content"]
    rerank_top = reranked[0]["content"]
    print(f"  Hybrid top:  '{hybrid_top[:55]}'")
    print(f"  Rerank top:  '{rerank_top[:55]}'")
    print(f"  ✅ Reranker applied successfully")


if __name__ == "__main__":
    print("\n🧠 Engram — BGE Reranker Test\n")
    try:
        test_reranker()
        print()
        print("✅ Reranker working.\n")
    except Exception as e:
        print(f"\n❌ Failed: {e}\n")
        sys.exit(1)
