"""
Engram — Embedder Test
Run from project root: python tests/test_embedder.py
"""
import sys
sys.path.append("backend")

from embedder import embedder

def test_embedder():
    print("  Testing single embed...")
    v1 = embedder.embed("Team decided API responses should use camelCase")
    assert len(v1) == 384, f"Expected 384 dims, got {len(v1)}"
    print(f"  ✅ Single embed  — {len(v1)} dimensions")

    print("  Testing batch embed...")
    texts = ["John leads the backend team", "Deadline is next Friday", "We use PostgreSQL"]
    vectors = embedder.embed_batch(texts)
    assert len(vectors) == 3
    print(f"  ✅ Batch embed   — {len(vectors)} vectors")

    print("  Testing similarity...")
    v2 = embedder.embed("API should return camelCase format")
    v3 = embedder.embed("I love eating pizza on weekends")
    sim_related = embedder.similarity(v1, v2)
    sim_unrelated = embedder.similarity(v1, v3)
    assert sim_related > sim_unrelated, "Related texts should score higher"
    print(f"  ✅ Similarity    — related: {sim_related:.3f} | unrelated: {sim_unrelated:.3f}")

if __name__ == "__main__":
    print("\n🧠 Engram — Embedder Test\n")
    try:
        test_embedder()
        print()
        print("✅ Embedder working.\n")
    except Exception as e:
        print(f"\n❌ Embedder failed: {e}\n")
        sys.exit(1)