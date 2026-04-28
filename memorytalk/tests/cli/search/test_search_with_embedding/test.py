"""`memory-talk search <query>` with a real OpenAI-compatible embedding.

Needs env var QWEN_KEY (DashScope API key). The fixture `openai_cli_env`
brings up an app whose `embedder` is `OpenAIEmbedder` pointing at
DashScope's `text-embedding-v4`. Every search call makes one real HTTP
POST to compute the query's vector; card creation makes another to
embed the summary.

Without QWEN_KEY → fixture setup fails (validate_embedder raises during
lifespan startup). That's the intended behavior; the test case fails,
not skips, so a missing credential cannot silently pass CI.
"""
from __future__ import annotations
import json

from memory_talk_v2.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest, IngestRound, IngestSessionRequest,
)


async def _seed(env):
    await env.app.state.sessions.ingest(IngestSessionRequest(
        session_id="platform-real", source="claude-code", created_at="",
        metadata={}, sha256="h-real",
        rounds=[IngestRound(
            round_id="r1", parent_id=None, timestamp="",
            speaker="user", role="human",
            content=[ContentBlock(type="text", text="we picked LanceDB for vector storage")],
            is_sidechain=False,
        )],
    ))
    await env.app.state.cards.create(CreateCardRequest(
        summary="selected LanceDB for embedded vector store",
        rounds=[CardRoundsItem(session_id="sess_platform-real", indexes="1")],
    ))


async def test_search_with_openai_embedding(openai_cli_env):
    """A real search round-trip: fixture boot probed DashScope successfully,
    seeding embedded the card summary for real, and the query itself gets
    a real embedding from DashScope before LanceDB does the hybrid match."""
    await _seed(openai_cli_env)

    result = openai_cli_env.runner.invoke(openai_cli_env.main, [
        "search", "LanceDB",
        "--data-root", str(openai_cli_env.config.data_root),
        "--json",
    ])
    assert result.exit_code == 0, f"search failed:\n{result.stdout}"
    out = json.loads(result.stdout)

    assert out["search_id"].startswith("sch_")
    assert out["query"] == "LanceDB"
    assert out["cards"]["count"] >= 1, out
    hit = out["cards"]["results"][0]
    assert hit["card_id"].startswith("card_")
    assert "LanceDB" in hit["summary"]

    # One CLI invocation → one SearchLog row
    assert (await openai_cli_env.app.state.db.search_log.count()) == 1
