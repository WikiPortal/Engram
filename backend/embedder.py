"""
Engram — Embedding Service
"""
from sentence_transformers import SentenceTransformer
from functools import lru_cache
import numpy as np


@lru_cache()
def _load_model(model_name: str) -> SentenceTransformer:
    """Load model once, reuse forever."""
    print(f"[Engram] Loading embedding model: {model_name} ...")
    model = SentenceTransformer(model_name)
    print(f"[Engram] Embedding model ready.")
    return model


class Embedder:

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.dim = 384

    def embed(self, text: str) -> list[float]:
        """Embed a single piece of text. Returns a list of 384 floats."""
        model = _load_model(self.model_name)
        vector = model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts at once — faster than one by one."""
        model = _load_model(self.model_name)
        vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return vectors.tolist()

    def similarity(self, v1: list[float], v2: list[float]) -> float:
        """Cosine similarity between two vectors. Returns 0.0 to 1.0."""
        a = np.array(v1)
        b = np.array(v2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


embedder = Embedder()