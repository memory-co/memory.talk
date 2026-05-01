"""Embedding providers and async startup validation.

dummy — deterministic hash, pure CPU, near-instant.
local — sentence-transformers (CPU/GPU). model.encode wrapped in asyncio.to_thread.
openai — OpenAI-compatible HTTP endpoint via httpx.AsyncClient.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from string import Template
import asyncio
import hashlib
import os
import httpx


def _resolve_auth_key(auth_key: str) -> str:
    """Render ``${VAR}`` env-var references in an auth key.

    Uses ``string.Template.substitute`` (strict, not safe_substitute) so
    a missing env var raises ``KeyError`` — callers turn that into a
    clear error rather than silently sending an empty Bearer. Strings
    without any ``$`` pass through untouched. Embed a literal ``$`` as
    ``$$`` if needed.
    """
    return Template(auth_key).substitute(os.environ)


class Embedder(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    async def embed_one(self, text: str) -> list[float]:
        out = await self.embed([text])
        return out[0]


class DummyEmbedder(Embedder):
    def __init__(self, dim: int = 384):
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Pure CPU, submillisecond — no need to offload.
        results = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            vec = [float(b) / 255.0 for b in h]
            vec = (vec * ((self.dim // len(vec)) + 1))[: self.dim]
            results.append(vec)
        return results


class LocalEmbedder(Embedder):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Model encode is CPU/GPU bound and can take 100ms+ — offload to a thread
        # so the event loop keeps moving.
        def _run():
            return self.model.encode(texts, convert_to_numpy=True).tolist()
        return await asyncio.to_thread(_run)


class OpenAIEmbedder(Embedder):
    """OpenAI-compatible embeddings over HTTP (OpenAI / DashScope / vLLM)."""

    def __init__(
        self,
        endpoint: str,
        auth_key: str,
        model: str,
        timeout: float = 30.0,
    ):
        if not endpoint:
            raise ValueError("OpenAIEmbedder requires an endpoint")
        if not auth_key:
            raise ValueError("OpenAIEmbedder requires an auth_key")
        self.endpoint = endpoint
        self.auth_key = auth_key
        self.model = model
        self.timeout = timeout

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            api_key = _resolve_auth_key(self.auth_key)
        except KeyError as e:
            raise RuntimeError(
                f"auth_key references env var ${{{e.args[0]}}} which is not set"
            ) from e
        if not api_key:
            raise RuntimeError("auth_key resolved to an empty string")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
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
            endpoint=emb.endpoint,
            auth_key=emb.auth_key,
            model=emb.model,
            timeout=emb.timeout,
        )
    raise ValueError(f"Unknown embedding provider: {p}")


class EmbedderValidationError(RuntimeError):
    """Raised at startup when the configured provider cannot be used."""


async def validate_embedder(config) -> None:
    """Fail-fast async probe."""
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
        try:
            api_key = _resolve_auth_key(emb.auth_key or "")
        except KeyError as e:
            raise EmbedderValidationError(
                f"openai embedder: auth_key references env var ${{{e.args[0]}}} "
                "which is not set"
            )
        if not api_key:
            raise EmbedderValidationError(
                "openai embedder: auth_key is empty (set a literal value or "
                "${VAR} in settings.json)"
            )
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    emb.endpoint,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": emb.model, "input": ["ping"], "encoding_format": "float"},
                    timeout=emb.timeout,
                )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data:
                raise EmbedderValidationError("openai embedder: probe response contained no data")
            probe_dim = len(data[0]["embedding"])
            if probe_dim != emb.dim:
                raise EmbedderValidationError(
                    f"openai embedder: dim mismatch — settings say {emb.dim}, endpoint returned {probe_dim}"
                )
        except EmbedderValidationError:
            raise
        except Exception as e:
            raise EmbedderValidationError(f"openai embedder: {e}") from e
        return

    raise EmbedderValidationError(f"unknown embedding provider: {p}")
