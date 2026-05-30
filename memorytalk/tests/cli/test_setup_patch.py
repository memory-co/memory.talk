"""Setup writes only what it prompts for; re-setup is a strict PATCH.

Bug being fixed: pre-0.8.x setup dumped pydantic-default values for
search / recall / explore into settings.json, which froze the values
at install time and prevented future default changes (e.g. the 0.8.2
``ranking_formula`` -> ``"relevance"`` switch) from reaching existing
installs.

New rule (these tests pin it):
  - setup owns exactly the fields it prompts for:
      server.port, vector.provider, relation.provider, embedding.*,
      sync.enabled
  - settings.json gets the owned fields and **nothing else** on first
    install — Settings model fills in everything else at load time
  - re-running setup PATCHes only owned fields; user customizations
    outside scope (e.g. embedding.batch_size = 5,
    sync.debounce_ms = 50, search.ranking_formula = "custom",
    explore.cwd = "/some/path", index.lance_flush_rows = 100) survive
"""
from __future__ import annotations
import json
import pathlib

import pytest
from click.testing import CliRunner


# ────────── _patch_owned unit ──────────

def test_patch_owned_overwrites_only_listed_keys():
    from memorytalk.cli.setup import _patch_owned
    base = {
        "embedding": {"provider": "openai", "model": "old", "dim": 1024,
                      "endpoint": "https://old", "auth_key": "OLD",
                      "timeout": 30.0, "batch_size": 5},
    }
    owned = {
        "embedding": {"provider": "local", "model": "new", "dim": 384},
    }
    out = _patch_owned(base, owned)
    # Listed keys overwritten.
    assert out["embedding"]["provider"] == "local"
    assert out["embedding"]["model"] == "new"
    assert out["embedding"]["dim"] == 384
    # Unlisted user customization preserved.
    assert out["embedding"]["batch_size"] == 5
    # Stale openai-specific fields stay (Option A — strict patch).
    assert out["embedding"]["endpoint"] == "https://old"
    assert out["embedding"]["auth_key"] == "OLD"


def test_patch_owned_leaves_other_sections_untouched():
    from memorytalk.cli.setup import _patch_owned
    base = {
        "server": {"port": 9000},
        "search": {"ranking_formula": "custom one"},
        "recall": {"default_top_k": 7},
        "explore": {"cwd": "/my/path"},
        "index": {"lance_flush_rows": 100},
    }
    owned = {"server": {"port": 7788}}
    out = _patch_owned(base, owned)
    assert out["server"]["port"] == 7788
    # Sections not in ``owned`` are returned byte-identical.
    assert out["search"] == {"ranking_formula": "custom one"}
    assert out["recall"] == {"default_top_k": 7}
    assert out["explore"] == {"cwd": "/my/path"}
    assert out["index"] == {"lance_flush_rows": 100}


def test_patch_owned_creates_missing_section():
    from memorytalk.cli.setup import _patch_owned
    base = {}
    owned = {"sync": {"enabled": True}}
    out = _patch_owned(base, owned)
    assert out == {"sync": {"enabled": True}}


def test_patch_owned_partial_section_merge():
    """``sync.enabled`` is owned but ``sync.debounce_ms`` is not —
    user customization of debounce_ms must survive a re-run."""
    from memorytalk.cli.setup import _patch_owned
    base = {"sync": {"enabled": False, "debounce_ms": 50}}
    owned = {"sync": {"enabled": True}}
    out = _patch_owned(base, owned)
    assert out["sync"] == {"enabled": True, "debounce_ms": 50}


# ────────── end-to-end: first-install writes only owned ──────────

def _wizard_stdin(*, model: str = "stub", dim: str = "384",
                  vector: str = "", relation: str = "", port: str = "",
                  sync_confirm: str = "y",
                  first_install: bool = False) -> str:
    """Compose the canned stdin sequence the dummy-embedder wizard
    expects. ``select dummy (1)`` is fixed for the embedding provider
    menu; the rest are textual prompts where blank = accept default.

    ``first_install=True`` appends an answer to the post-write
    "Start the server now?" prompt that only fires on first install.
    ``n`` to skip (don't actually launch the daemon in a test).
    """
    # Order must match _wizard prompts exactly:
    # embedding provider menu → 1 (dummy)
    # embedding model → blank
    # embedding dim → blank
    # vector provider → blank
    # relation provider → blank
    # server port → blank
    # sync confirm → y/n
    base = f"1\n{model}\n{dim}\n{vector}\n{relation}\n{port}\n{sync_confirm}\n"
    if first_install:
        base += "n\n"  # don't launch the daemon
    return base


def _register_dummy_embedder():
    """Make the dummy embedder selectable in the wizard menu."""
    import memorytalk.cli.setup as setup_mod
    from memorytalk.util import console
    # Idempotent: don't double-add across tests.
    if any(getattr(o, "label", o) == "dummy" for o in setup_mod._EMB_OPTIONS):
        return
    setup_mod._EMB_OPTIONS = [
        console.Option("dummy", description="deterministic hash, tests only"),
        *setup_mod._EMB_OPTIONS,
    ]


def test_first_install_writes_only_owned_fields(tmp_path, monkeypatch):
    """No settings.json yet → wizard writes one with only the prompted
    sections / fields. search / recall / explore / index sections must
    be absent so Settings model defaults track schema updates."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    _register_dummy_embedder()

    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(
        main, ["setup"], input=_wizard_stdin(first_install=True),
    )
    assert result.exit_code == 0, result.output

    raw = json.loads((tmp_path / "settings.json").read_text())

    # Owned sections present.
    assert set(raw.keys()) == {"server", "vector", "relation", "embedding", "sync"}

    # Owned-sub-keys-only inside sync — no debounce_ms materialized.
    assert raw["sync"] == {"enabled": True}

    # search / recall / explore / index absent entirely.
    for absent in ("search", "recall", "explore", "index"):
        assert absent not in raw, f"unprompted section {absent!r} got materialized"


def test_first_install_embedding_carries_only_prompted_keys(tmp_path, monkeypatch):
    """For embedding=dummy, wizard prompts provider/model/dim — the
    rest of EmbeddingConfig (endpoint/auth_key/timeout/batch_size)
    must not appear on first install."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    _register_dummy_embedder()

    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["setup"], input=_wizard_stdin(first_install=True))
    assert result.exit_code == 0

    emb = json.loads((tmp_path / "settings.json").read_text())["embedding"]
    assert set(emb.keys()) == {"provider", "model", "dim"}


# ────────── end-to-end: re-setup PATCHes, preserves user fields ──────────

def test_resetup_preserves_unprompted_user_customizations(tmp_path, monkeypatch):
    """User has manually added settings outside setup's scope — those
    MUST survive a second setup run. This is the headline regression
    of the field-level PATCH rule."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    _register_dummy_embedder()

    # Pre-seed: user-customized fields setup doesn't know about.
    (tmp_path / "settings.json").write_text(json.dumps({
        "server": {"port": 7788},
        "vector": {"provider": "lancedb"},
        "relation": {"provider": "sqlite"},
        "embedding": {"provider": "dummy", "model": "stub",
                      "dim": 384, "batch_size": 5},   # ← user's tuning
        "sync": {"enabled": True, "debounce_ms": 50}, # ← user's tuning
        "search": {"ranking_formula": "review_up"},   # ← user's custom
        "recall": {"default_top_k": 7},               # ← user's choice
        "explore": {"cwd": "/some/path"},             # ← user's path
        "index": {"lance_flush_rows": 100},           # ← user's tuning
    }))

    from memorytalk.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["setup"], input=_wizard_stdin())
    assert result.exit_code == 0, result.output

    raw = json.loads((tmp_path / "settings.json").read_text())

    # Owned fields reflect wizard's collected values.
    assert raw["embedding"]["provider"] == "dummy"
    assert raw["sync"]["enabled"] is True

    # Unprompted user values preserved verbatim.
    assert raw["embedding"]["batch_size"] == 5
    assert raw["sync"]["debounce_ms"] == 50
    assert raw["search"] == {"ranking_formula": "review_up"}
    assert raw["recall"] == {"default_top_k": 7}
    assert raw["explore"] == {"cwd": "/some/path"}
    assert raw["index"] == {"lance_flush_rows": 100}


def test_resetup_overwrites_owned_when_changed(tmp_path, monkeypatch):
    """Wizard changing a prompted field → that field is updated; other
    fields in the same section stay."""
    monkeypatch.setenv("MEMORY_TALK_DATA_ROOT", str(tmp_path))
    _register_dummy_embedder()

    (tmp_path / "settings.json").write_text(json.dumps({
        "server": {"port": 9999},
        "vector": {"provider": "lancedb"},
        "relation": {"provider": "sqlite"},
        "embedding": {"provider": "dummy", "model": "old-model",
                      "dim": 384, "batch_size": 5},
        "sync": {"enabled": False, "debounce_ms": 50},
    }))

    from memorytalk.cli import main
    runner = CliRunner()
    # Set new model name in the prompt; accept defaults for everything else.
    result = runner.invoke(
        main, ["setup"],
        input=_wizard_stdin(model="new-model", port="7788", sync_confirm="y"),
    )
    assert result.exit_code == 0, result.output

    raw = json.loads((tmp_path / "settings.json").read_text())
    # Prompted fields overwritten.
    assert raw["server"]["port"] == 7788
    assert raw["embedding"]["model"] == "new-model"
    assert raw["sync"]["enabled"] is True
    # Unprompted fields in the same sections preserved.
    assert raw["embedding"]["batch_size"] == 5
    assert raw["sync"]["debounce_ms"] == 50
