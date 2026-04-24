"""`memory-talk search <query>` — plain keyword search, no DSL filter.

Focus: the CLI → httpx → FastAPI → SearchService → LanceDB → response
round-trip. This is NOT a ranking/relevance test — we just assert the
response shape is right and the query reaches cards that contain the
term. Quality of ranking is covered by a separate test layer.
"""
from __future__ import annotations
import json

from memory_talk_v2.schemas import (
    CardRoundsItem, ContentBlock, CreateCardRequest, IngestRound, IngestSessionRequest,
)


async def _seed(cli_env):
    """Seed 2 sessions + 1 card — one about LanceDB, one unrelated."""
    for sid_raw, text in [
        ("platform-db", "we picked LanceDB for vector storage"),
        ("platform-bug", "fixed a jsonl parser bug yesterday"),
    ]:
        await cli_env.app.state.sessions.ingest(IngestSessionRequest(
            session_id=sid_raw, source="claude-code", created_at="",
            metadata={}, sha256=f"h-{sid_raw}",
            rounds=[IngestRound(
                round_id=f"{sid_raw}_r1", parent_id=None, timestamp="",
                speaker="user", role="human",
                content=[ContentBlock(type="text", text=text)],
                is_sidechain=False,
            )],
        ))
    await cli_env.app.state.cards.create(CreateCardRequest(
        summary="selected LanceDB for embedded vector store",
        rounds=[CardRoundsItem(session_id="sess_platform-db", indexes="1")],
    ))


async def _run_search(cli_env, query: str, top_k: int | None = None) -> tuple[int, dict]:
    args = ["search", query, "--data-root", str(cli_env.config.data_root)]
    if top_k is not None:
        args += ["--top-k", str(top_k)]
    result = cli_env.runner.invoke(cli_env.main, args)
    return result.exit_code, json.loads(result.stdout)


async def test_search_returns_structured_response(cli_env):
    await _seed(cli_env)

    exit_code, out = await _run_search(cli_env, "LanceDB")
    assert exit_code == 0, out

    # Wire-format contract
    assert out["search_id"].startswith("sch_"), out
    assert out["query"] == "LanceDB"
    assert "cards" in out and "sessions" in out
    assert "count" in out["cards"] and "results" in out["cards"]
    assert "count" in out["sessions"] and "results" in out["sessions"]
    assert out["cards"]["count"] == len(out["cards"]["results"])
    assert out["sessions"]["count"] == len(out["sessions"]["results"])


async def test_search_finds_the_matching_card(cli_env):
    await _seed(cli_env)

    _, out = await _run_search(cli_env, "LanceDB")
    # The seeded card summary contains "LanceDB" — it should be a hit.
    # Don't assert exact rank/score; just that SOMETHING came back on the cards side.
    assert out["cards"]["count"] >= 1, out
    # Each hit has the fields the handler's response_model promises
    hit = out["cards"]["results"][0]
    for key in ("card_id", "rank", "score", "summary", "snippets", "links"):
        assert key in hit, f"missing {key!r} in card hit: {hit}"
    assert hit["card_id"].startswith("card_")
    assert isinstance(hit["rank"], int)
    assert isinstance(hit["snippets"], list)


async def test_search_persists_search_log(cli_env):
    await _seed(cli_env)

    before = await cli_env.app.state.db.search_log.count()
    await _run_search(cli_env, "LanceDB")
    after = await cli_env.app.state.db.search_log.count()
    # One CLI invocation = one SearchLog row
    assert after == before + 1


async def test_search_respects_top_k(cli_env):
    await _seed(cli_env)

    _, out = await _run_search(cli_env, "LanceDB", top_k=1)
    # Whatever came back, count is capped by top_k per bucket
    assert out["cards"]["count"] <= 1
    assert out["sessions"]["count"] <= 1
