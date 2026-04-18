"""Server crash diagnostics — verify error capture on startup failure."""
import json
import sys

import pytest
from click.testing import CliRunner

from memory_talk.cli import server_start
from memory_talk.config import Config


class TestServerCrash:
    def test_start_captures_failure(self, temp_root):
        """When uvicorn fails to start, server start should report status=failed with error details."""
        config = Config(temp_root)
        config.ensure_dirs()

        bad_script = temp_root / "bad_server.py"
        bad_script.write_text(
            'import sys\n'
            'sys.stderr.write("ImportError: No module named broken_module\\n")\n'
            'sys.exit(1)\n'
        )

        runner = CliRunner()
        import subprocess
        original_popen = subprocess.Popen

        class FakePopen:
            def __init__(self, cmd, **kwargs):
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

        assert not config.pid_path.exists()
