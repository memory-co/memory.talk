"""auto_split — 长 doc 透明分块场景. See README.md."""
from __future__ import annotations

from memorytalk.config import Config
from memorytalk.searchbase import Doc, Query
from memorytalk.tests.searchbase.local.conftest import make_backend


async def test_auto_split_collection_hides_chunking(data_root):
    """25 字符的 text + max_text_length=10 → 内部 3 个 chunk 行,
    但 count / search / delete 对外仍以 1 个逻辑 doc 呈现。
    内部 chunk id (``n1#0``) 永远不流出。"""
    config = Config(data_root)
    config.ensure_dirs()
    b = await make_backend(
        config,
        collections={"notes": {"fields": {}, "auto_split": True}},
        max_text_length=10,
    )
    try:
        await b.upsert("notes", [Doc(id="n1", text="alpha beta gamma delta eps")])
        assert await b.count("notes") == 1

        hits = await b.search("notes", Query(text="gamma", top_k=5))
        ids = [h.id for h in hits]
        assert ids.count("n1") == 1, "collapsed, not three chunk hits"
        assert "n1#0" not in ids, "internal chunk ids must never leak"

        await b.delete("notes", ["n1"])
        assert await b.count("notes") == 0, "all chunks gone"
    finally:
        await b.close()
