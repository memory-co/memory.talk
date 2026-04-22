"""Server lifecycle: start → status → stop → status."""
import json
import random
import time

import pytest
from click.testing import CliRunner

from memory_talk.cli import main
from memory_talk.config import Config
from memory_talk.storage.init_db import init_db


class TestServerLifecycle:
    def test_start_status_stop(self, temp_root):
        """Full lifecycle: start → status(running) → stop → status(not_running)."""
        # Use random port to avoid conflicts
        port = random.randint(19000, 19999)

        config = Config(temp_root)
        config.ensure_dirs()
        # Write settings with random port
        config._settings = config._load()
        config._settings.server.port = port
        config.save()
        init_db(config.db_path)

        runner = CliRunner()
        data_root = str(temp_root)

        # 1. Start (reads port from settings)
        result = runner.invoke(main, ["server", "start", "--data-root", data_root])
        assert result.exit_code == 0
        start_data = json.loads(result.output)
        assert start_data["status"] == "started"
        assert start_data["port"] == port
        pid = start_data["pid"]

        time.sleep(1)

        try:
            # 2. Status — API reachable on configured port
            result = runner.invoke(main, ["server", "status", "--data-root", data_root])
            assert result.exit_code == 0
            status_data = json.loads(result.output)
            assert status_data["status"] == "running"
            assert status_data["data_root"] == data_root
            assert "sessions_total" in status_data

            # 3. Start again — already_running
            result = runner.invoke(main, ["server", "start", "--data-root", data_root])
            assert result.exit_code == 0
            assert json.loads(result.output)["status"] == "already_running"

            # 4. Stop
            result = runner.invoke(main, ["server", "stop", "--data-root", data_root])
            assert result.exit_code == 0
            assert json.loads(result.output)["status"] == "stopped"

            time.sleep(0.5)

            # 5. Status after stop — not_running
            result = runner.invoke(main, ["server", "status", "--data-root", data_root])
            assert result.exit_code == 0
            assert json.loads(result.output)["status"] == "not_running"

            # 6. PID file gone
            assert not config.pid_path.exists()

        finally:
            import os
            import signal
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            config.pid_path.unlink(missing_ok=True)
