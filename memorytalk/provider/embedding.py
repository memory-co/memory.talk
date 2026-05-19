"""Embedding providers and async startup validation.

- ``dummy`` — deterministic hash, pure CPU. Tests only.
- ``local`` — sentence-transformers (CPU/GPU); ``encode`` runs in a thread.
- ``openai`` — OpenAI-compatible HTTP endpoint via httpx.AsyncClient.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import asyncio
import hashlib

import httpx


class Embedder(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]:
        out = await self.embed([text])
        return out[0]


class DummyEmbedder(Embedder):
    """Deterministic SHA-256-derived vectors. Submillisecond, no I/O."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h]
            vec = (vec * ((self.dim // len(vec)) + 1))[: self.dim]
            out.append(vec)
        return out


class LocalEmbedder(Embedder):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # encode() is CPU/GPU bound; offload so the event loop keeps moving.
        def _run():
            return self.model.encode(list(texts), convert_to_numpy=True).tolist()
        return await asyncio.to_thread(_run)


class OpenAIEmbedder(Embedder):
    """OpenAI-compatible embeddings over HTTP (OpenAI / DashScope / vLLM)."""

    def __init__(self, endpoint: str, auth_key: str, model: str, timeout: float = 30.0):
        if not endpoint:
            raise ValueError("OpenAIEmbedder requires an endpoint")
        if not auth_key:
            raise ValueError("OpenAIEmbedder requires an auth_key")
        self.endpoint = endpoint
        self.auth_key = auth_key
        self.model = model
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.auth_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "input": list(texts), "encoding_format": "float"},
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
    if p == "local":
        return LocalEmbedder(emb.model)
    if p == "openai":
        return OpenAIEmbedder(
            endpoint=emb.endpoint, auth_key=emb.auth_key,
            model=emb.model, timeout=emb.timeout,
        )
    raise ValueError(f"unknown embedding provider: {p}")


class EmbedderValidationError(RuntimeError):
    """Raised at startup when the configured provider cannot be used."""


async def validate_embedder(config) -> None:
    """Fail-fast async probe; called from the FastAPI lifespan."""
    emb = config.settings.embedding
    p = emb.provider

    if p == "dummy":
        return

    if p == "local":
        try:
            from sentence_transformers import SentenceTransformer
            def _load():
                return SentenceTransformer(emb.model)
            await asyncio.to_thread(_load)
        except Exception as e:
            raise EmbedderValidationError(
                f"local embedder failed to load model {emb.model!r}: {e}"
            ) from e
        return

    if p == "openai":
        if not emb.auth_key:
            raise EmbedderValidationError("openai embedder: auth_key is empty")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    emb.endpoint,
                    headers={
                        "Authorization": f"Bearer {emb.auth_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": emb.model, "input": ["ping"], "encoding_format": "float"},
                    timeout=emb.timeout,
                )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data:
                raise EmbedderValidationError("openai embedder: probe response had no data")
            probe_dim = len(data[0]["embedding"])
            if probe_dim != emb.dim:
                raise EmbedderValidationError(
                    f"openai embedder: dim mismatch — settings say {emb.dim}, "
                    f"endpoint returned {probe_dim}"
                )
        except EmbedderValidationError:
            raise
        except Exception as e:
            raise EmbedderValidationError(f"openai embedder: {e}") from e
        return

    raise EmbedderValidationError(f"unknown embedding provider: {p}")
