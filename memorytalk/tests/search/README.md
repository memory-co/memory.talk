# tests/search — 搜索质量回归

跟其他测试树不同,这里测的不是"代码契约对不对",而是"**搜索结果好不好**" ——
一个连续质量信号,映射到 5 档 pytest 状态。

## 数据流

```
tests/search/corpus/                  # 提交进 repo 的 file-layer fixture
  sessions/<source>/<bucket>/sess_<label>/{meta.json, rounds.jsonl}
  cards/<bucket>/card_<label>/card.json
                  │
                  │ shutil.copytree
                  ▼
        <tmp_data_root>/
                  │
                  │ POST /v2/rebuild  (computes embeddings via real DashScope)
                  ▼
            SQLite + LanceDB + FTS index
                  │
                  │ POST /v2/search  (per probe)
                  ▼
              hits → MRR → quality_gate
```

整套用真实 DashScope embedding(`auth_env_key=QWEN_KEY`),**没设 key 直接 FAIL**,
不 skip。

## 模式

| 目录 | 探针目标 | 走的搜索路径 |
|---|---|---|
| `pure_fts/` | `sess_<label>` | sessions 桶 (FTS-only by design) |
| `fts_plus_vector/` | `card_<label>` | cards 桶 (FTS + vector → RRF) |

每个模式下 4 个 case:`test_en_single_word` / `test_en_multi_word` /
`test_zh_single_word` / `test_zh_multi_word`。两边的 case 列表是独立的,
后续会按需要发散。

## 质量分级 (`_quality.py`)

每个 case 跑探针集,按 MRR 求均值得到 0..1 分数:

| 区间 | 等级 | pytest 表现 |
|---|---|---|
| ≥ 0.9 | Excellent | pass + baseline 更新(只在 `UPDATE_BASELINES=1` 时写盘)|
| 0.7-0.9 | Acceptable | pass |
| 0.5-0.7 | Marginal | pass + `warnings.warn` |
| 0.3-0.5 | Degraded | `pytest.xfail("known weak")` |
| < 0.3 | Failed | `AssertionError` |

Baseline 容差 = 0.10:某 case 之前 0.95,这次跑出 0.86 仍然算通过(噪声宽容)。
跌得更狠才会 FAIL。`_baselines.json` 是版本化的,改阈值/改 corpus 后用
`UPDATE_BASELINES=1` 重新刷一次,人工 review 提交。

## 增删 corpus

数据在 `_corpus.py::TOPICS` 定义。改了之后跑一次 regen 把 file-layer 文件刷新:

```bash
python3 -m memory_talk_v2.tests.search._corpus
```

然后跑测试看分数变化,需要的话 `UPDATE_BASELINES=1` 更新 baseline。
