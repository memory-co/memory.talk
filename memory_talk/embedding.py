"""Embedding abstraction — pure math, no LLM cognition."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class LocalEmbedder(Embedder):
    """Local sentence-transformers embedder."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()


class DummyEmbedder(Embedder):
    """Fixed-dimension dummy embedder for testing."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        results = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h]
            # pad or truncate to dim
            vec = (vec * ((self.dim // len(vec)) + 1))[:self.dim]
            results.append(vec)
        return results


def get_embedder(backend: str = "local", model_name: str = "all-MiniLM-L6-v2") -> Embedder:
    if backend == "local":
        return LocalEmbedder(model_name)
    elif backend == "dummy":
        return DummyEmbedder()
    else:
        raise ValueError(f"Unknown embedding backend: {backend}")
