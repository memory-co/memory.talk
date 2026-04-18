"""Embedding abstraction — pure math, no LLM."""
from __future__ import annotations
from abc import ABC, abstractmethod
import hashlib

class Embedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...
    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

class DummyEmbedder(Embedder):
    def __init__(self, dim: int = 384):
        self.dim = dim
    def embed(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h]
            vec = (vec * ((self.dim // len(vec)) + 1))[:self.dim]
            results.append(vec)
        return results

class LocalEmbedder(Embedder):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, convert_to_numpy=True).tolist()

def get_embedder(config) -> Embedder:
    p = config.settings.embedding.provider
    if p == "dummy":
        return DummyEmbedder()
    elif p == "local":
        return LocalEmbedder(config.settings.embedding.model)
    raise ValueError(f"Unknown embedding provider: {p}")
