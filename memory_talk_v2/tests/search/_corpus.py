"""Search-quality corpus: source-of-truth + fixture regenerator.

Strategy: corpus lives as real file-layer fixtures under
``tests/search/corpus/{sessions,cards}/...`` (committed to the repo). At
test time conftest copies the fixture tree into a tmp data root and calls
``/v2/rebuild`` — exactly like a fresh server starting from disk truth.

This module's only job is to (re)bake the fixture tree from the TOPICS
table. It is NOT imported at test time. Run manually when adding/editing
topics:

    python -m memory_talk_v2.tests.search._corpus

Each TOPICS entry yields TWO objects with parallel deterministic IDs:
- session ``sess_<label>`` — single round whose content is the topic body
- card ``card_<label>`` — short summary referencing that round

The two trees can pick different probe targets later as they diverge.
"""
from __future__ import annotations
import json
import shutil
from pathlib import Path


TOPICS: list[dict] = [
    # English
    {"label": "lancedb",
     "summary": "LanceDB introduction",
     "content": "LanceDB is a fully managed embedded vector database with built-in "
                "FTS support and zero operational overhead."},
    {"label": "fastapi_mw",
     "summary": "FastAPI middleware patterns",
     "content": "FastAPI middleware patterns: write request-scoped middleware to gate "
                "endpoints, log latency, and inject context via the @app.middleware decorator."},
    {"label": "pinecone",
     "summary": "Pinecone vector database review",
     "content": "Pinecone is a hosted vector database; we reviewed pricing, namespaces, "
                "and the tradeoff vs running an embedded engine ourselves."},
    {"label": "postgres",
     "summary": "PostgreSQL deep dive",
     "content": "PostgreSQL deep dive: MVCC internals, vacuum pressure, planner statistics, "
                "and how to read EXPLAIN ANALYZE output."},
    {"label": "k8s",
     "summary": "Kubernetes deployment notes",
     "content": "Kubernetes deployment patterns: Pod, Service, Deployment, ConfigMap, "
                "and how to roll out updates safely with Helm or Kustomize."},
    {"label": "vector_compare",
     "summary": "Vector database comparison",
     "content": "Vector database comparison: LanceDB vs Pinecone vs Chroma — embedded, "
                "managed, and developer-experience axes; LanceDB wins for our use case."},
    {"label": "async_middleware",
     "summary": "Async Python middleware design",
     "content": "Async python middleware design: yielding control around blocking IO, "
                "structuring lifespan teardown, and avoiding sync calls inside event loops."},
    {"label": "memory_talk_intro",
     "summary": "Memory talk skill overview",
     "content": "Memory talk skill overview: a Skill (not a service) that turns chat history "
                "into searchable cards, with the LLM doing cognition and the CLI doing data ops."},
    {"label": "fts_design",
     "summary": "FTS inverted index implementation",
     "content": "FTS inverted index implementation notes: tokenizer choice, posting list "
                "compression, and how positional info enables phrase queries."},
    {"label": "rebuild_design",
     "summary": "Rebuild from file truth design",
     "content": "Rebuild from file truth design: SQLite and LanceDB are derived from the "
                "JSONL files on disk, so a corruption can be recovered by replaying."},
    # Chinese
    {"label": "vector_db_zh",
     "summary": "向量数据库综述",
     "content": "向量数据库综述:对比 LanceDB、Pinecone、Chroma 在嵌入式、托管、"
                "开发体验三个维度上的取舍,以及典型应用场景。"},
    {"label": "search_engine_zh",
     "summary": "搜索引擎核心原理",
     "content": "搜索引擎核心原理:倒排索引、TF-IDF、BM25 评分,以及与向量召回融合的现代检索系统设计。"},
    {"label": "async_zh",
     "summary": "异步编程模型详解",
     "content": "异步编程模型详解:event loop、协程、await 语义,以及与线程池的协作模式。"},
    {"label": "embedded_zh",
     "summary": "嵌入式系统开发流程",
     "content": "嵌入式系统的开发流程,从硬件选型到固件烧录、内存约束、外设驱动的协调,"
                "以及实时调度的考量。"},
    {"label": "fts_zh",
     "summary": "全文检索引擎对比",
     "content": "全文检索引擎对比:Elasticsearch、OpenSearch、LanceDB FTS 的索引结构差异 "
                "和运维成本对比。"},
    {"label": "zh_fts_decision",
     "summary": "中文全文检索选型决策",
     "content": "中文全文检索选型决策:jieba 预分词加 whitespace tokenizer 是当前最稳的组合,"
                "兼容 LanceDB FTS,且对查询端的中文切分行为可预测。"},
    {"label": "async_db_pool_zh",
     "summary": "异步数据库连接池实现",
     "content": "异步数据库连接池实现:aiosqlite 的连接复用、超时控制、以及失败重连的语义,"
                "重点处理 cancel 时的资源释放。"},
    {"label": "vector_rebuild_zh",
     "summary": "向量索引重建流程",
     "content": "向量索引重建流程:drop 表、清空 SQLite、从文件层重填,最后重建 FTS 倒排索引,"
                "全程在 rebuilding 状态下拒绝并发写。"},
    {"label": "code_review_zh",
     "summary": "代码评审流程规范",
     "content": "代码评审流程规范:小步提交、PR 描述模板、必备 reviewer 矩阵,以及合并门禁。"},
    {"label": "perf_monitoring_zh",
     "summary": "性能监控告警体系",
     "content": "性能监控和告警体系:Prometheus 抓取、Grafana 仪表板、告警规则触发条件,"
                "以及告警去重和静默策略,避免告警疲劳。"},
]


# Stable timestamps so committed fixtures don't churn in git diff on regen.
CREATED_AT = "2026-04-25T00:00:00Z"
EXPIRES_AT = "2030-04-25T00:00:00Z"
SOURCE = "claude-code"


def _bucket(raw_id: str) -> str:
    raw = raw_id[len("sess_"):] if raw_id.startswith("sess_") else \
          raw_id[len("card_"):] if raw_id.startswith("card_") else raw_id
    return (raw[:2] if len(raw) >= 2 else raw).lower()


def _session_meta(session_id: str, round_count: int) -> dict:
    return {
        "session_id": session_id,
        "source": SOURCE,
        "created_at": CREATED_AT,
        "metadata": {},
        "tags": [],
        "round_count": round_count,
        "synced_at": CREATED_AT,
    }


def _session_round(idx: int, content: str) -> dict:
    return {
        "idx": idx,
        "round_id": f"r{idx}",
        "parent_id": None,
        "timestamp": "",
        "speaker": "user",
        "role": "human",
        "content": [{"type": "text", "text": content, "thinking": None}],
        "is_sidechain": False,
        "cwd": None,
        "usage": None,
    }


def _card_doc(card_id: str, summary: str, content: str, src_session_id: str) -> dict:
    return {
        "card_id": card_id,
        "summary": summary,
        "rounds": [{
            "role": "human",
            "text": content,
            "thinking": "",
            "session_id": src_session_id,
            "index": 1,
        }],
        "created_at": CREATED_AT,
        "expires_at": EXPIRES_AT,
    }


def regen_fixtures(corpus_root: Path) -> None:
    """Re-bake the entire fixture tree under ``corpus_root``.

    Wipes the existing tree and writes fresh files for every TOPICS entry.
    """
    sessions_root = corpus_root / "sessions"
    cards_root = corpus_root / "cards"
    if sessions_root.exists():
        shutil.rmtree(sessions_root)
    if cards_root.exists():
        shutil.rmtree(cards_root)

    for topic in TOPICS:
        sid = f"sess_{topic['label']}"
        cid = f"card_{topic['label']}"
        sess_dir = sessions_root / SOURCE / _bucket(sid) / sid
        sess_dir.mkdir(parents=True, exist_ok=True)
        (sess_dir / "meta.json").write_text(
            json.dumps(_session_meta(sid, 1), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (sess_dir / "rounds.jsonl").write_text(
            json.dumps(_session_round(1, topic["content"]), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        card_dir = cards_root / _bucket(cid) / cid
        card_dir.mkdir(parents=True, exist_ok=True)
        (card_dir / "card.json").write_text(
            json.dumps(_card_doc(cid, topic["summary"], topic["content"], sid),
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    here = Path(__file__).parent
    regen_fixtures(here / "corpus")
    print(f"baked {len(TOPICS)} topics → {here / 'corpus'}")
