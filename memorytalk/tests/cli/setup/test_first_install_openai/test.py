"""First-install with openai provider — mocked HTTP probe.

Setup no longer takes --data-root; the conftest patches Path.home() to
a tmp dir so the default ~/.memory-talk path lands under tmp.
"""
from __future__ import annotations
import json


def test_first_install_openai_writes_settings(setup_env):
    setup_env.mock_openai_probe(dim=1024)

    setup_env.prompts.extend([
        "openai",                                                              # provider select
        "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",        # endpoint select
        "${QWEN_KEY}",                                                         # auth_key text (env-var ref)
        "text-embedding-v4",                                                   # model select (dim 1024 auto)
        "",                                                                    # port text → default
        "yes",                                                                 # start server select
    ])

    result = setup_env.runner.invoke(setup_env.main, ["setup"])

    assert result.exit_code == 0, (result.stdout, result.exception)

    settings_path = setup_env.data_root / "settings.json"
    assert settings_path.exists()
    data = json.loads(settings_path.read_text())
    assert data["embedding"]["provider"] == "openai"
    assert data["embedding"]["model"] == "text-embedding-v4"
    assert data["embedding"]["dim"] == 1024
    assert data["embedding"]["auth_key"] == "${QWEN_KEY}"
    assert data["server"]["port"] == 7788
    assert data["vector"]["provider"] == "lancedb"
    assert data["relation"]["provider"] == "sqlite"

    for sub in ("sessions", "cards", "links", "vectors", "logs/search"):
        assert (setup_env.data_root / sub).exists()

    assert "# setup · **ok**" in result.stdout
    assert "openai" in result.stdout
    assert "text-embedding-v4" in result.stdout
    # Probe 成功反馈行 —— conftest 把 err_console.file 绑到 env.stderr_buf，
    # 因为 rich.Console 在模块导入时锁定了真实 sys.stderr 引用，绕开了
    # CliRunner 的重定向。
    err = setup_env.stderr()
    assert "embedding verified" in err
    assert "dim 1024" in err
    # mock 的 httpx probe 同步返回 → 延迟必然 < 1s，单位一定是 "ms"
    assert "ms" in err

    # Wizard called the Claude hook step (stubbed to skipped in conftest).
    assert len(setup_env.claude_hook_calls) == 1, (
        "wizard did not call _step_claude_hook"
    )
    # Summary table has a `claude hook | skipped (stubbed in tests)` row.
    # The regex anchors the assertion to the row label so a "skipped" from
    # any other row (e.g. PATH takeover) cannot satisfy it.
    import re
    assert re.search(
        r"\|\s*claude hook\s*\|\s*skipped \(stubbed in tests\)\s*\|",
        result.stdout,
    ), result.stdout
