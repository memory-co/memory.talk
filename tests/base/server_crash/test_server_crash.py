"""Story 04: Server crash diagnostics — verify error capture on startup failure."""
import json
import sys
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from memory_talk.cli import server_start, server_status
from memory_talk.config import Config


class TestServerCrash:
    def test_start_captures_failure(self, temp_root):
        """When uvicorn fails to start, server start should report status=failed with error details."""
        config = Config(temp_root)
        config.ensure_dirs()

        # Create a broken launcher script that exits immediately with an error
        bad_script = temp_root / "bad_server.py"
        bad_script.write_text(
            'import sys\n'
            'sys.stderr.write("ImportError: No module named broken_module\\n")\n'
            'sys.exit(1)\n'
        )

        runner = CliRunner()
        # Invoke with --data-root so it uses our temp dir;
        # We monkey-patch sys.executable usage by patching subprocess.Popen
        import subprocess
        original_popen = subprocess.Popen

        class FakePopen:
            """Intercept Popen to run our broken script instead of uvicorn."""
            def __init__(self, cmd, **kwargs):
                # Replace the command with our broken script
                kwargs.pop('start_new_session', None)
                self._proc = original_popen(
                    [sys.executable, str(bad_script)],
                    **kwargs,
                )
                self.pid = self._proc.pid

            def poll(self):
                return self._proc.poll()

        import unittest.mock
        with unittest.mock.patch('memory_talk.cli.subprocess.Popen', FakePopen):
            result = runner.invoke(server_start, ['--data-root', str(temp_root), '--port', '19999'])

        output = result.output.strip()
        data = json.loads(output)
        assert data["status"] == "failed"
        assert data["exit_code"] == 1
        assert "broken_module" in data["error"]

        # PID file should NOT exist after failure
        assert not config.pid_path.exists()

    def test_status_shows_crashed(self, temp_root):
        """When server.log has content and no PID file, status should report crashed."""
        config = Config(temp_root)
        config.ensure_dirs()

        # Write a fake crash log
        log_path = config.data_root / "server.log"
        log_path.write_text("Traceback (most recent call last):\n  RuntimeError: bind failed\n")

        # No PID file exists
        assert not config.pid_path.exists()

        runner = CliRunner()
        result = runner.invoke(server_status, ['--data-root', str(temp_root)])

        output = result.output.strip()
        data = json.loads(output)
        assert data["status"] == "crashed"
        assert "bind failed" in data["error"]

    def test_status_not_running_without_log(self, temp_root):
        """When no PID file and no server.log, status should report not_running."""
        config = Config(temp_root)
        config.ensure_dirs()

        runner = CliRunner()
        result = runner.invoke(server_status, ['--data-root', str(temp_root)])

        output = result.output.strip()
        data = json.loads(output)
        assert data["status"] == "not_running"
