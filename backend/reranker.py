"""
Engram — BGE Reranker (Step 12)
Cross-encoder precision pass after hybrid search.
Model: BAAI/bge-reranker-base (free, runs locally, ~1.1GB download once)
Semantic drift — reranker catches results that look relevant but aren't.
"""
from sentence_transformers import CrossEncoder
from functools import lru_cache
from config import get_settings

settings = get_settings()


@lru_cache()
def _load_reranker(model_name: str) -> CrossEncoder:
    print(f"[Engram] Loading reranker: {model_name} ...")
    model = CrossEncoder(model_name)
    print(f"[Engram] Reranker ready.")
    return model


def rerank(query: str, candidates: list[dict], top_k: int = None) -> list[dict]:
    """
    Rerank candidates using BGE cross-encoder.
    Each candidate must have a 'content' field.
    Returns top_k candidates sorted by rerank score descending.
    """
    if not candidates:
        return []

    if top_k is None:
        top_k = settings.top_k_reranked

    model = _load_reranker(settings.reranker_model)

    # Cross-encoder scores query+document pairs jointly
    pairs = [(query, c["content"]) for c in candidates]
    scores = model.predict(pairs)

    # Attach rerank score to each candidate
    for i, candidate in enumerate(candidates):
        candidate["rerank_score"] = round(float(scores[i]), 4)

    # Sort by rerank score descending
    reranked = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)

    return reranked[:top_k]
