"""OpenAIEmbedder chunked embed — guards against the DashScope 10-batch
silent-failure mode that motivated the 0.6.1 fix.

We mock httpx.AsyncClient so the test is offline + deterministic. The
fixture's mock asserts each request body's ``input`` length is ≤ the
configured batch_size; the actual embedding values are placeholder
floats keyed off the position so failure modes show up in test diffs.
"""
from __future__ import annotations

import pytest
from unittest import mock

from memorytalk.provider.embedding import OpenAIEmbedder


def _mock_response(payload: dict, status: int = 200):
    """Build a mock httpx.Response with .raise_for_status / .json."""
    resp = mock.MagicMock()
    resp.status_code = status
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    else:
        resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def _embed_payload_for(chunk: list[str]) -> dict:
    """Mimic OpenAI's response: each entry has an index + a synthetic
    embedding so the test can verify positional correctness."""
    return {
        "data": [
            {"index": i, "embedding": [float(i)] * 3}
            for i in range(len(chunk))
        ]
    }


class TestChunking:

    @pytest.mark.asyncio
    async def test_single_batch_under_cap_one_request(self):
        emb = OpenAIEmbedder(
            endpoint="http://x/embed", auth_key="k", model="m", batch_size=10,
        )
        captured = []
        with mock.patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            async def post(url, headers=None, json=None, timeout=None):
                captured.append(json["input"])
                return _mock_response(_embed_payload_for(json["input"]))
            client.post.side_effect = post
            out = await emb.embed([f"t{i}" for i in range(7)])

        assert len(out) == 7
        # 7 ≤ 10 → one request, one chunk.
        assert len(captured) == 1
        assert len(captured[0]) == 7

    @pytest.mark.asyncio
    async def test_chunks_when_over_cap(self):
        """11 inputs with batch_size=10 → two POSTs of size 10 + 1.
        This is the DashScope-cap regression case."""
        emb = OpenAIEmbedder(
            endpoint="http://x/embed", auth_key="k", model="m", batch_size=10,
        )
        captured = []
        with mock.patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            async def post(url, headers=None, json=None, timeout=None):
                captured.append(len(json["input"]))
                return _mock_response(_embed_payload_for(json["input"]))
            client.post.side_effect = post
            out = await emb.embed([f"t{i}" for i in range(11)])

        assert len(out) == 11
        assert captured == [10, 1]

    @pytest.mark.asyncio
    async def test_chunks_preserve_order(self):
        """Concatenation across chunks must keep the caller-supplied
        order — out[i] is always the embedding of texts[i]."""
        emb = OpenAIEmbedder(
            endpoint="http://x/embed", auth_key="k", model="m", batch_size=5,
        )
        # Each chunk's embedding[0] = its position within the chunk; if
        # we accidentally concatenated chunks out of order, the
        # numbers would be scrambled.
        with mock.patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            async def post(url, headers=None, json=None, timeout=None):
                return _mock_response(_embed_payload_for(json["input"]))
            client.post.side_effect = post
            out = await emb.embed([f"t{i}" for i in range(13)])

        assert len(out) == 13
        # Within each chunk the index resets, so expected pattern is
        # [0,1,2,3,4, 0,1,2,3,4, 0,1,2]. We only care that the result
        # has 13 elements concatenated in chunk order — easier check.
        # 4th element should be from chunk 0 (index 4), 5th from chunk 1 (index 0).
        assert out[0] == [0.0, 0.0, 0.0]   # chunk 0, index 0
        assert out[4] == [4.0, 4.0, 4.0]   # chunk 0, index 4
        assert out[5] == [0.0, 0.0, 0.0]   # chunk 1, index 0
        assert out[12] == [2.0, 2.0, 2.0]  # chunk 2, index 2 (last of 13)

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty_no_request(self):
        emb = OpenAIEmbedder(
            endpoint="http://x/embed", auth_key="k", model="m", batch_size=10,
        )
        with mock.patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            client.post.side_effect = AssertionError("should not be called")
            out = await emb.embed([])
        assert out == []

    @pytest.mark.asyncio
    async def test_failing_chunk_aborts_call(self):
        """Mid-chunk failure raises; partial-success semantics belong
        to the caller (IngestService), not the embedder."""
        emb = OpenAIEmbedder(
            endpoint="http://x/embed", auth_key="k", model="m", batch_size=5,
        )
        call_count = [0]
        with mock.patch("httpx.AsyncClient") as mock_client_cls:
            client = mock_client_cls.return_value.__aenter__.return_value
            async def post(url, headers=None, json=None, timeout=None):
                call_count[0] += 1
                if call_count[0] == 2:
                    return _mock_response({"error": "boom"}, status=400)
                return _mock_response(_embed_payload_for(json["input"]))
            client.post.side_effect = post
            with pytest.raises(Exception):
                await emb.embed([f"t{i}" for i in range(11)])
        # First chunk succeeded but result is discarded — caller has to
        # detect the partial state on its own (we don't return it).
        assert call_count[0] == 2

    def test_invalid_batch_size_rejected(self):
        with pytest.raises(ValueError, match="batch_size"):
            OpenAIEmbedder(
                endpoint="http://x/embed", auth_key="k", model="m", batch_size=0,
            )
