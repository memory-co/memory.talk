# memory-talk search 排序问题 · 现场报告

- 日期：2026-05-22
- 仓库：`memory.talk`（branch `main`，HEAD `2b71226`）
- 复现命令：`memory-talk search "你可以分析一下这个项目吗？"`
- 数据目录：`~/.memory-talk/sessions/`
- 结论：**最匹配（精确字符串匹配）的会话被排在第 2 位**，根因是 RRF 输出尺度 + noisy-OR 聚合公式的语义错配，并非召回环节问题。

---

## 1. 现象

执行：

```bash
memory-talk search "你可以分析一下这个项目吗？"
```

返回排序（取 JSON，按 `final_score` 降序）：

| rank | session | hit_count | 最强单 hit | final_score |
|---:|---|---:|---:|---:|
| **1** | `sess_e9440bff…`（**当前对话**自身） | **14** | 0.031545 | **0.302588** |
| **2** | `sess_c31f653c…`（**期望的最佳匹配**） | 4 | 0.031545 | 0.078702 |
| 3 | `sess_dc152960…` | 3 | 0.030090 | 0.068413 |
| 4 | `sess_84a932f9…` | 4 | 0.012195 | 0.041438 |
| 5 | `sess_0a294181…` | 3 | 0.012987 | 0.033375 |
| 6 | `sess_ad6ac803…` | 2 | 0.022984 | 0.031659 |

注意：

- **#1 和 #2 的"最强单 hit"分数完全相同**（`0.031545`）。
- 它们之间 `final_score` 差 **3.8×**，纯靠 `hit_count` 拉开。

## 2. 期望行为

`sess_c31f653c` 第 4 轮原始文本如下（直接读 `rounds.jsonl`）：

```
idx:   4
role:  human
text:  '你可以分析一下这个项目吗？'
```

这是**整轮 = 查询字符串**的完美精确匹配（无任何噪声字符），用户期望它排第 1。

## 3. 实际数据：两个会话的 hit 构成

### 3.1 `sess_e9440bff…`（当前会话，被错误排到 #1）

`rounds.jsonl` 共 83 轮，其中 **14 轮命中**，全部来自"当前会话本身正在做这次调试"产生的复读：

| idx | role | 节选 |
|---:|---|---|
| 4 | human | "…执行命令 memory-talk search \"你可以分析一下这个项目吗？\" 搜索的时候…" |
| 9 | human | （切换 model 后用户**再次发送**了同样的话） |
| 28 | assistant | `TaskCreate description` 里转写了 query |
| 38 | assistant | `Bash command` 里把 query 当参数 |
| 39 | human | 上一条 Bash 的 stdout（包含搜索结果中的 query） |
| 40 | assistant | 我的中间分析（提到了 query） |
| 53, 67, 69, 71, 74 | assistant | 更多 Bash / grep 命令，都带 query |
| 75 | human | grep stdout |
| 82 | assistant | 总结回答（提到 query） |

→ 这些都不是用户在历史里真正"问过的相似问题"，而是**当前调试动作产生的回声**。

### 3.2 `sess_c31f653c…`（期望排第 1，实际 #2）

`rounds.jsonl` 共 35 轮，**只有 1 处命中**——而且是干净的精确匹配（见 §2）。Top 3 hits：

| 顺位 | score | 说明 |
|---:|---:|---|
| 1 | 0.031545 | idx=4，整轮就是 query 本身 |
| 2 | 0.025397 | 弱相关 |
| 3 | 0.013514 | 弱相关 |

## 4. 根因

两个独立层的 bug 叠加。

### 4.1 起因 A：RRF 分数尺度极小且分布扁平

`memorytalk/provider/lancedb.py:208`

```python
q = q.rerank(reranker=RRFReranker(K=60))
```

RRF 公式：`score(d) = Σ_list 1/(K + rank_in_list(d))`，K=60。

- 上限（两路均排第 1）：`2/61 ≈ 0.0328`
- 第 1 名 vs 第 2 名：`1/61 − 1/62 ≈ 0.0003`

**完美匹配 vs "沾点边的匹配" 在 RRF 输出层的差距只有 1% 量级**。

### 4.2 起因 B：noisy-OR 聚合在小输入下退化为加法

`memorytalk/service/search.py:71-86`

```python
def _aggregate_session_relevance(scores: list[float]) -> float:
    """1 - prod(1 - s_i): bounded 'any of them' aggregator.

    Multiple round hits in the same session multiply the chance that
    *some* round of this session matches, with diminishing returns. Maps
    to [0, 1] and never exceeds the strongest single hit by much.
    """
    if not scores:
        return 0.0
    p = 1.0
    for s in scores:
        s = max(0.0, min(1.0, s))
        p *= (1.0 - s)
    return 1.0 - p
```

docstring 描述的契约是"**对各 hit 概率求 OR，有 diminishing returns，绝不会比最强 hit 大多少**"。这个契约只在输入接近 1 时成立。

对小输入 s ≪ 1，泰勒展开：

```
1 − ∏(1 − s_i)  ≈  Σ s_i − Σ_{i<j} s_i·s_j  ≈  Σ s_i
```

实测：

```
10 个 0.03 → noisy-or = 0.2626,  sum = 0.3000  （差距 12%）
```

→ 在 RRF 尺度下，noisy-OR **本质等同于求和**，"diminishing returns"区到不了，结果可以远远超过最强单 hit。

### 4.3 两层叠加 ⇒ "多 hit 就赢"

代入本案：

| session | hit_count | 聚合 ≈ Σ hits | JSON final_score |
|---|---:|---:|---:|
| `sess_e9440bff…` | 14 | ≈ 0.302 | **0.302588** |
| `sess_c31f653c…` | 4 | ≈ 0.080 | 0.078702 |

公式：`final_score = relevance − 0.005 × age_days`。两个会话都是今天的（age ≈ 0），所以 `final_score ≈ relevance`，**唯一区别就是 hit 数量**。

**简言之：当前会话因为正在调试这件事本身，复读了 14 次 query，于是聚合后的 relevance 高 3.8×，把真正的精确匹配挤到了第 2。**

## 5. 影响范围

任何"查询在某个会话里被回声/转述多次"的情况都会触发：

- **当前会话**几乎一定会出现在第 1（因为用户刚说过、Claude 刚转写过）。
- 多轮长对话里被反复引用的话题会强压"单次清晰提问"。
- 用户问"我之前问过 XXX 吗？"——往往返回的不是当年那次提问，而是后来反复讨论 XXX 的某次长会话。

## 6. 修复方向（候选，未实施）

| 方案 | 思路 | 优点 | 风险 |
|---|---|---|---|
| **A. 改聚合公式：max + 衰减加成** | `agg = max(s_i) + α·Σ_{i>1} s_i`（α 取 0.1-0.3） | 直接保证"最强 hit 主导"，符合用户预期 | 需调 α |
| **B. RRF 分归一化后再聚合** | 先 `s_i' = s_i / (2/(K+1))` 映到 [0,1]，再喂 noisy-OR | 让 docstring 描述的契约真正成立 | 仍可能被"满会话弱命中"打过；改动语义不大 |
| **C. 按 hit_count 加对数惩罚** | `agg' = agg / log(1 + hit_count)` | 直接打击"复读会话" | 治标，且会误伤"真的相关多次"的会话 |
| **D. 过滤当前会话** | 在 `_collect_session_candidates` 里跳过调用者的 session | 解掉最常见的现象 | 治标，不是当前调用方所属那次会话也会有同类问题 |

倾向 **A**（最直接命中用户直觉），其次 **B**（修聚合语义本身的 bug）。两者可组合。

## 7. 附录：复现 & 验证脚本

### 7.1 复现

```bash
memory-talk search "你可以分析一下这个项目吗？" --json | python3 -c "
import json, sys
for r in json.load(sys.stdin)['results'][:6]:
    if 'session_id' in r:
        print(f\"rank={r['rank']} score={r['score']:.4f} sess={r['session_id'][:20]} \"
              f\"hits={r['hit_count']} top_hit={r['hits'][0]['score']:.4f}\")
"
```

### 7.2 聚合公式行为验证

```python
def noisy_or(scores):
    p = 1.0
    for s in scores: p *= (1 - s)
    return 1 - p

# RRF 尺度（≤0.033）下 noisy-or ≈ sum
print(noisy_or([0.03]*10), sum([0.03]*10))   # 0.2626  0.3000
print(noisy_or([0.03]*14), sum([0.03]*14))   # 0.3479  0.4200

# 完美 hit + 弱 hit  vs  纯弱 hit 堆
print(noisy_or([0.032, 0.025, 0.014, 0.010]))                # 0.0790
print(noisy_or([0.030]*14))                                  # 0.3493
```

### 7.3 关键源码定位

- 聚合公式：`memorytalk/service/search.py:71-86`（`_aggregate_session_relevance`）
- session relevance 写入：`memorytalk/service/search.py:243-251`
- 排序：`memorytalk/service/search.py:150`（`merged.sort(key=lambda x: x[1]["final_score"], reverse=True)`）
- 评分公式：`memorytalk/service/search.py:256-273`（`_score`）
- 默认 ranking_formula：`memorytalk/config.py:19-22`
- RRF reranker：`memorytalk/provider/lancedb.py:208`
