"""Config.validate — accepts empty root, rejects v1 residue."""
from __future__ import annotations
import sqlite3

import pytest

from memory_talk_v2.config import Config, ConfigValidationError


def test_validate_passes_on_empty_root(tmp_path):
    Config(tmp_path / ".mt").validate()  # no memory.db yet


def test_validate_rejects_v1_residue(tmp_path):
    root = tmp_path / ".mt"
    root.mkdir()
    # Simulate v1 residue by creating a recall_log table
    conn = sqlite3.connect(root / "memory.db")
    conn.execute("CREATE TABLE recall_log (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    with pytest.raises(ConfigValidationError) as e:
        Config(root).validate()
    assert "recall_log" in str(e.value)
