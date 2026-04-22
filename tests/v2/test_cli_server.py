from click.testing import CliRunner


def test_v2_cli_has_server_group(monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_CLI_VERSION", "v2")
    import importlib
    import memory_talk.cli
    importlib.reload(memory_talk.cli)
    from memory_talk.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["server", "--help"])
    assert result.exit_code == 0
    assert "start" in result.output
    assert "stop" in result.output
    assert "status" in result.output


def test_v2_cli_server_status_without_server(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_CLI_VERSION", "v2")
    monkeypatch.setenv("HOME", str(tmp_path))
    import importlib
    import memory_talk.cli
    importlib.reload(memory_talk.cli)
    from memory_talk.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["server", "status"])
    assert result.exit_code == 0
    assert "not_running" in result.output


def test_v2_server_start_fails_loudly_on_bad_embedding(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TALK_CLI_VERSION", "v2")
    monkeypatch.delenv("UNIT_TEST_KEY", raising=False)

    # Configure openai embedding with a missing env var — this should make
    # the spawned uvicorn process exit 2 at startup and the CLI should surface it.
    data_root = tmp_path / ".memory-talk"
    data_root.mkdir(parents=True)
    (data_root / "settings.json").write_text(
        '{"embedding": {"provider": "openai", "endpoint": "https://x/v1/embeddings",'
        ' "auth_env_key": "UNIT_TEST_KEY", "model": "x", "dim": 1024}}'
    )

    import importlib
    import memory_talk.cli
    importlib.reload(memory_talk.cli)
    from memory_talk.cli import main
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(main, ["server", "start", "--data-root", str(data_root)])
    # CLI surfaces a failed server start with non-zero exit code + error payload.
    assert result.exit_code != 0
    assert "failed" in result.output
    assert "UNIT_TEST_KEY" in result.output
