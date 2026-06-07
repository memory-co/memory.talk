# auto_split — 长 doc 切块对调用方不可见

## 这个场景在测什么

声明 `auto_split: True` 的 collection 写入一个超过 `max_text_length` 的
doc 时,searchbase **在内部**把 doc 切成多个 chunk 行(每行带 `_base_id`
+ `_chunk` 隐藏列)。这一切对调用方应该是**完全不可见**的:

| 操作 | 期望行为 |
|---|---|
| `count` | 按逻辑 doc 数,不是 chunk 行数 |
| `search` | 同一 doc 的多 chunk 收敛回一个 hit,不暴露 chunk id (`n1#0` 这种) |
| `delete` | 用逻辑 doc id 一删,所有 chunk 行一起没 |

## 为什么单独一个场景

跟 `basic_io` 共用一个 `cards` 也能跑,但 collection spec 不同
(`auto_split: True`),fixture 不一样,而且这是个独立 feature
("透明分块"),逻辑上应该跟基本读写分开。

## 不在这测什么

- chunking 的内部 split 算法(`split_text` / `collapse_chunks`)走单测覆盖,
  不在场景测试里重复
- chunk 写入的 fragment 数 / compaction 行为走 `compaction/`
