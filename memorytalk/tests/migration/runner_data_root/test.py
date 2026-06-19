"""runner_data_root -- migrations accept the data_root kwarg the runner passes. See README.md."""
from __future__ import annotations

import aiosqlite
import pytest

from memorytalk.migrations.v1 import init_database as v1_init
from memorytalk.migrations.v2 import up_database as v2_up


@pytest.mark.asyncio
async def test_v1_init_and_v2_up_accept_data_root_kwarg():
    conn = await aiosqlite.connect(":memory:")
    await v1_init.run(conn, data_root=None)   # must accept the kwarg now
    await v2_up.run(conn, data_root=None)
    await conn.close()
