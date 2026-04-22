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
