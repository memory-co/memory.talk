- 日期：2026-05-23
- 仓库：`memory.talk`（branch `main`，HEAD `6ac967a`）
- 复现命令：`memory-talk search "你可以分析一下这个项目吗？"`
- 数据目录：`~/.memory-talk/sessions/`
- LanceDB 版本：`0.30.2`
- 结论：**v1 报告（HEAD `2b71226`）里的"noisy-OR 聚合 bug"已经在 commit `6ac967a` 修复；但同一个 commit 顺手把 reranker 从 `RRFReranker(K=60)` 换成了 `LinearCombinationReranker()`，新 reranker 在 LanceDB 当前实现下把"完美精确匹配"从 #2 推到了 #2639，连召回都进不了。**

---

## 0. 与 v1 报告的关系

[`2026-05-21-search-noisy-or-aggregation-bug.md`](2026-05-21-search-noisy-or-aggregation-bug.md)（HEAD `2b71226`）总结的是修复**之前**的状态：

- 旧根因 A：`RRFReranker(K=60)` 输出尺度极小（top ~0.033）且扁平
- 旧根因 B：`_aggregate_session_relevance` 用 noisy-OR，小输入下退化为求和
- 旧症状：完美匹配 `sess_c31f653c…` 被"复读 query 的当前会话"靠 14 个弱 hit 总和挤到 **#2**

commit `6ac967a "fix(search): max-aggregator + LinearCombination reranker"` 做了两层改：

1. 聚合：`noisy-OR → max`（`memorytalk/service/search.py:71-95`）
2. Reranker：`RRFReranker(K=60) → LinearCombinationReranker()`（`memorytalk/provider/lancedb.py:222`）

**第 1 层修对了**（本会话 13 个 hits 也只排到 #6，max 在工作）。**第 2 层引入了新的更严重的 bug**——完美匹配从委屈到 #2 变成完全消失。本报告专门讲第 2 层。

---

## 1. 现象

`memory-talk search "你可以分析一下这个项目吗？"` 当前 top 10：

| rank | session | hits | top_hit | final_score | 说明 |
|---:|---|---:|---:|---:|---|
| 1 | `sess_a17ab5bb…` | 1 | 0.9826 | 0.9779 | 仅有"你好"的会话 |
| 2 | `sess_0a294181…` | 3 | 0.9659 | 0.9561 | 讨论 AONE_SANDBOX_ID 时带过"分析"两字 |
| 3 | `sess_ad6ac803…` | 1 | 0.9537 | 0.9437 | 仅有"你好"的会话 |
| 4 | `sess_ba5f11dd…` | 1 | 0.9512 | 0.9354 | 仅有"你好"的会话 |
| 5 | `sess_9af3440b…` | 2 | 0.9589 | 0.8710 | 仅有"你好" + "创建新应用" |
| 6 | `sess_e9440bff…`（**当前调试会话**） | 13 | 0.8763 | 0.8704 | 13 hits 也没上来 → max 起作用了 |
| 7 | `sess_01da6f1c…` | 1 | 0.9512 | 0.8453 | — |
| 8 | `sess_79cbc0ca…` | 1 | 0.9863 | 0.8390 | "@rootfs (2).tar.gz 帮我把这个文件解压…" |
| 9 | `sess_68837195…` | 4 | 0.9875 | 0.8375 | — |
| 10 | `sess_bb935334…` | 1 | 0.9773 | 0.8368 | — |

期望的 #1 是 `sess_c31f653c-c046-4772-b6f5-11adf0ec2e94`——它的 idx=4 round 原文就是 `'你可以分析一下这个项目吗？'`，**整轮完美等于 query**。

**它没出现在 top 10。也没出现在 top 50（即 `_ROUNDS_OVERSAMPLE=5 × top_k=10` 的召回上限）。事实上它连 top 1000 都进不了。**

---

## 2. 证据链

固定 query / 固定数据（`~/.memory-talk/sessions/...` 现状），观察"完美匹配 `sess_c31f653c idx=4`"在不同检索路径下的排名：

| 检索路径 | 完美匹配排名 | 第 1 名 |
|---|---:|---|
| **BM25 only** (`table.query().nearest_to_text(...)`) | **#9**（BM25 = 34.93） | `sess_e9440bff idx=88`（本会话刚刚的 grep stdout） |
| **Vector only** (`table.query().nearest_to(qvec)`) | **#1**（distance = 0.0000） | 自己 |
| **Hybrid，无 reranker**（LanceDB 默认 = RRF） | **#2**（`_relevance_score = 0.0307`） | `sess_e9440bff idx=88` |
| **Hybrid + `LinearCombinationReranker()`，limit=50（线上配置）** | **找不到** | `sess_e9440bff idx=92`，`rel=1.0000`，`dist=None`，`bm=31.11` |
| **同上，limit=10000** | **#2639**（`rel=0.0554`，`dist=0.0000`，`bm=34.00`） | 同上 |

→ BM25 单独识别得出（#9），Vector 单独识别得出（#1），**两条腿"加起来"反而把它推到 2600 名外**。这是 reranker 自身的问题，跟召回数据完整性、跟聚合公式都无关。

---

## 3. 根因：LinearCombinationReranker 的量纲错配 + fill 反向

`lancedb==0.30.2`，`lancedb/rerankers/linear_combination.py` 关键代码：

```python
class LinearCombinationReranker(Reranker):
    """
    fill : float, default 1.0
        The score to give to results that are only in one of the two result sets.
        This is treated as penalty, so a higher value means a lower score.
        TODO: We should just hardcode this--
        its pretty confusing as we invert scores to calculate final score
    """
    def __init__(self, weight=0.7, fill=1.0, return_score='relevance'):
        ...

    def merge_results(self, vector_results, fts_results, fill):
        ...
        for row_id, result in results.items():
            vector_score = self._invert_score(result.get("_distance", fill))
            fts_score = result.get("_score", fill)
            result["_relevance_score"] = self._combine_score(vector_score, fts_score)
        ...

    def _combine_score(self, vector_score, fts_score):
        # these scores represent distance
        return 1 - (self.weight * vector_score + (1 - self.weight) * fts_score)

    def _invert_score(self, dist):
        return 1 - dist
```

注意三处反直觉：

1. **`vector_score = 1 - distance`** —— 实际是余弦相似度（`[0, 1]`），但注释和后续公式按"距离"处理；
2. **`fts_score = result["_score"]`** —— 直接是 BM25 **原始分**（无界正分，本例中典型 30+），没归一化；
3. **`return 1 - (0.7 · vec + 0.3 · bm)`** —— 把"相似度"和"BM25 原始分"线性加权后再 `1 - ...`，等价于把 BM25 越高的 hit 越往低分推。

### 3.1 代入本例

| 行类型 | `dist` | `vec = 1 - dist` | `bm` | `_combine = 1 - (0.7·vec + 0.3·bm)` |
|---|---:|---:|---:|---:|
| **完美匹配 `c31f653c idx=4`** | 0.000 | 1.0 | 34.00 | `1 - (0.70 + 10.20)` = **−9.90** |
| Top hybrid #1（`e9440bff idx=92`） | None→fill=1 | 1−1=0 | 31.11 | `1 - (0    +  9.33)` = **−8.33** |
| 完全不相关弱命中 | 0.5 | 0.5 | None→fill=1 | `1 - (0.35 +  0.30)` = **+0.35** |

LanceDB 把这一列再 min-max 归一化到 `[0, 1]`，于是：

- 完美匹配的 `−9.90` → 归一化后接近 `0.05`（实测 0.0554）
- "只 BM25 命中、BM25 中等强、没进 vector 召回"的 hit → 归一化后接近 `1.0`（实测 1.0000）
- 真正完全不相关、但碰巧两边都有弱信号的 → 排在最前 `[0.99, 1.0]`

**净效果：BM25 越强、向量越准，最终 `_relevance_score` 越接近 0。**这跟 commit `6ac967a` 的 message 里说的"`LinearCombination` 用真实 BM25 + 向量分，'score 高 = 强匹配'才有意义"**正好相反**。

### 3.2 LanceDB 上游自己也承认

上面那段 docstring 里的 `TODO`：

> `TODO: We should just hardcode this -- its pretty confusing as we invert scores to calculate final score`

上游知道这个 reranker 的 score-inversion + `fill` 语义混乱，只是还没改。

### 3.3 我们这边为什么"刚好踩中"

commit `6ac967a` 切到 LinearCombination 时假设的是"BM25 分高 = 匹配强"，这在**直观语义**上对，但在 LanceDB 当前实现下不成立——根本原因是 BM25 原始分（无界）和 cosine 相似度（`[0,1]`）尺度差两个数量级，公式又把两者按错误的方向加权。文本越是"query 子串"的精确匹配，BM25 越高，被压得越狠。这一类 query 是 search 最应该擅长的，结果反而最差。

---

## 4. 影响范围

只要 query 在某条 round 里出现得**密集且完整**（完美/接近完美的 BM25 命中），这条 round 就会被新 reranker 系统性地压到召回外。具体场景：

- 用户问"我之前问过 XXX 吗？" —— 当年那次原话提问会被压掉，返回的是后来讨论 XXX 的长会话；
- 复述老问题做对照 —— 老问题原文找不到；
- 任何**短文本 + 强精确匹配**的 round —— BM25 满分反而是惩罚。

旧的 noisy-OR bug 还在的时候至少"完美匹配排 #2"；现在直接消失。从用户视角看是一次**回归**。

---

## 5. 修复方向

| 方案 | 思路 | 优点 | 风险 |
|---|---|---|---|
| **A. Reranker 回退到 RRF** | `q.rerank(reranker=RRFReranker(K=60))`（或直接不传，走 LanceDB hybrid 默认） | 立刻让完美匹配回到 #2；保留 `max` 聚合，旧 noisy-OR bug 不会回来 | 失去"用真实分数"的初衷，但本来 LinearCombination 也没真正做到 |
| **B. 自写归一化 LinearCombination** | reranker 前对 BM25 在召回内 min-max 到 `[0,1]`，再调 LinearCombination 或自己加权 | 真正实现 commit `6ac967a` 想要的"按真实分加权" | 自己实现 reranker，要测；min-max 在小召回集里也不稳 |
| **C. 换 CrossEncoderReranker** | LanceDB 自带 cross-encoder 选项 | 语义层更强 | 引入模型依赖、延迟、成本 |
| **D. 等 LanceDB 上游修** | 跟 `TODO` 那行 | 不动代码 | 时间不可控；线上一直坏着 |

倾向 **A**——它就是 cherry-pick `6ac967a` 的一半：聚合公式从 noisy-OR 改成 max 留下，reranker 改回 RRF。两个 bug 都解掉。一旦 LanceDB 上游修了 LinearCombination 或我们写好 **B**，再切回来。

### 5.1 最小修复 patch（参考）

`memorytalk/provider/lancedb.py:201-222`：

```diff
-    from lancedb.rerankers import LinearCombinationReranker
+    from lancedb.rerankers import RRFReranker
     ...
     if has_vector and has_text:
-        q = q.rerank(reranker=LinearCombinationReranker())
+        q = q.rerank(reranker=RRFReranker(K=60))
```

聚合层不动（`_aggregate_session_relevance` 已经是 `max`，可继续抗住 RRF 的扁平输出 + 多 hit 复读）。

---

## 6. 复现 & 验证脚本

### 6.1 顶层复现

```bash
memory-talk search "你可以分析一下这个项目吗？" --json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for r in d['results']:
    if r.get('session_id', '').startswith('sess_c31f653c'):
        print('found:', r['rank'], r['score']); break
else:
    print('NOT FOUND in top', len(d['results']))
"
# 期望输出: 'found: 1 0.99xx'
# 实际输出: 'NOT FOUND in top 10'
```

### 6.2 直接验证 reranker 行为

```python
# /Users/zzz/.memory-talk/.venv/bin/python3.12
import asyncio
from memorytalk.config import Config
from memorytalk.provider.lancedb import LanceStore, _segment
from memorytalk.provider.embedding import get_embedder
from lancedb.rerankers import LinearCombinationReranker

QUERY = "你可以分析一下这个项目吗？"
TARGET = ("sess_c31f653c-c046-4772-b6f5-11adf0ec2e94", 4)

async def main():
    cfg = Config()
    store = await LanceStore.create(cfg.vectors_dir, dim=cfg.settings.embedding.dim)
    embedder = get_embedder(cfg)
    qvec = await embedder.embed_one(QUERY)
    await store.ensure_fts_index(LanceStore.ROUNDS)
    table = await store.db.open_table(LanceStore.ROUNDS)

    # A. BM25 only — 完美匹配应该在 #9
    rows = await table.query().nearest_to_text(_segment(QUERY)).limit(20).to_list()
    for i, r in enumerate(rows, 1):
        if (r["session_id"], r["idx"]) == TARGET:
            print(f"BM25 only:   rank #{i}, bm25={r['_score']:.2f}"); break

    # B. Vector only — 完美匹配应该在 #1
    rows = await table.query().nearest_to(qvec).limit(20).to_list()
    for i, r in enumerate(rows, 1):
        if (r["session_id"], r["idx"]) == TARGET:
            print(f"Vector only: rank #{i}, distance={r['_distance']:.4f}"); break

    # C. Hybrid no reranker (LanceDB default = RRF) — 完美匹配应该在 #2
    rows = await table.query().nearest_to(qvec).nearest_to_text(_segment(QUERY)).limit(500).to_list()
    for i, r in enumerate(rows, 1):
        if (r["session_id"], r["idx"]) == TARGET:
            print(f"Hybrid default (RRF): rank #{i}, rel={r['_relevance_score']:.4f}"); break

    # D. Hybrid + LinearCombination — 完美匹配在 #2639
    q = table.query().nearest_to(qvec).nearest_to_text(_segment(QUERY))
    q = q.rerank(reranker=LinearCombinationReranker(return_score='all')).limit(10000)
    rows = await q.to_list()
    for i, r in enumerate(rows, 1):
        if (r["session_id"], r["idx"]) == TARGET:
            print(f"Hybrid + LinearCombination: rank #{i}, rel={r['_relevance_score']:.4f}, "
                  f"dist={r.get('_distance')}, bm={r.get('_score')}"); break

asyncio.run(main())
```

预期输出（实测）：

```
BM25 only:                    rank #9,    bm25=34.93
Vector only:                  rank #1,    distance=0.0000
Hybrid default (RRF):         rank #2,    rel=0.0307
Hybrid + LinearCombination:   rank #2639, rel=0.0554, dist=0.0, bm=34.00
```

### 6.3 关键源码定位

- 当前 reranker 选择：`memorytalk/provider/lancedb.py:222` — `LinearCombinationReranker()`
- 聚合公式（已修复为 max）：`memorytalk/service/search.py:71-95` — `_aggregate_session_relevance`
- 召回 oversample 因子：`memorytalk/service/search.py:45` — `_ROUNDS_OVERSAMPLE = 5`
- `default_top_k`：`memorytalk/config.py:50` — `10`（→ 召回上限 50）
- LanceDB 上游 reranker：`<venv>/lib/python3.12/site-packages/lancedb/rerankers/linear_combination.py`
