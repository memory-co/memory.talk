"""Embedding abstraction — pure math, no LLM."""
from __future__ import annotations
from abc import ABC, abstractmethod
import hashlib
import os
import httpx

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

class OpenAIEmbedder(Embedder):
    """OpenAI-compatible embeddings over HTTP (e.g. OpenAI, DashScope, vLLM)."""

    def __init__(
        self,
        endpoint: str,
        auth_env_key: str,
        model: str,
        timeout: float = 30.0,
    ):
        if not endpoint:
            raise ValueError("OpenAIEmbedder requires an endpoint")
        if not auth_env_key:
            raise ValueError("OpenAIEmbedder requires an auth_env_key")
        self.endpoint = endpoint
        self.auth_env_key = auth_env_key
        self.model = model
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        api_key = os.environ.get(self.auth_env_key)
        if not api_key:
            raise RuntimeError(
                f"Environment variable {self.auth_env_key} is not set"
            )
        resp = httpx.post(
            self.endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": list(texts),
                "encoding_format": "float",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        data_sorted = sorted(data, key=lambda d: d["index"])
        return [d["embedding"] for d in data_sorted]


def get_embedder(config) -> Embedder:
    emb = config.settings.embedding
    p = emb.provider
    if p == "dummy":
        return DummyEmbedder(dim=emb.dim)
    elif p == "local":
        return LocalEmbedder(emb.model)
    elif p == "openai":
        return OpenAIEmbedder(
            endpoint=emb.endpoint,
            auth_env_key=emb.auth_env_key,
            model=emb.model,
            timeout=emb.timeout,
        )
    raise ValueError(f"Unknown embedding provider: {p}")
