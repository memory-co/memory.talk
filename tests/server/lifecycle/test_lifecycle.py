"""Server lifecycle: start → status → stop → status."""
import json
import time

import pytest
from click.testing import CliRunner

from memory_talk.cli import main
from memory_talk.config import Config
from memory_talk.storage.init_db import init_db


class TestServerLifecycle:
    def test_start_status_stop(self, temp_root):
        """Full lifecycle: start → status(running) → stop → status(not_running)."""
        config = Config(temp_root)
        config.ensure_dirs()
        config.save()
        init_db(config.db_path)

        runner = CliRunner()
        data_root = str(temp_root)
        port = "18899"

        # 1. Start
        result = runner.invoke(main, ["server", "start", "--data-root", data_root, "--port", port])
        assert result.exit_code == 0
        start_data = json.loads(result.output)
        assert start_data["status"] == "started"
        pid = start_data["pid"]
        assert pid > 0

        # Give server a moment to fully start
        time.sleep(1)

        try:
            # 2. Status — should be running with data_root and settings_path
            result = runner.invoke(main, ["server", "status", "--data-root", data_root])
            assert result.exit_code == 0
            status_data = json.loads(result.output)
            assert status_data["status"] == "running"
            assert status_data["pid"] == pid
            assert status_data["data_root"] == data_root
            assert "settings_path" in status_data

            # 3. Start again — should say already_running
            result = runner.invoke(main, ["server", "start", "--data-root", data_root, "--port", port])
            assert result.exit_code == 0
            again_data = json.loads(result.output)
            assert again_data["status"] == "already_running"

            # 4. Stop
            result = runner.invoke(main, ["server", "stop", "--data-root", data_root])
            assert result.exit_code == 0
            stop_data = json.loads(result.output)
            assert stop_data["status"] == "stopped"

            time.sleep(0.5)

            # 5. Status after stop — not_running
            result = runner.invoke(main, ["server", "status", "--data-root", data_root])
            assert result.exit_code == 0
            final_data = json.loads(result.output)
            assert final_data["status"] == "not_running"

            # 6. PID file should be gone
            assert not config.pid_path.exists()

        finally:
            # Cleanup: make sure server is stopped even if test fails
            import os
            import signal
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            config.pid_path.unlink(missing_ok=True)
