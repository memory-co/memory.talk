# test_extract_basics

`extract_snippets(text, query)` 的英文/常规路径 —— 空 query、命中、不命中。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_empty_query_returns_empty` | `extract_snippets("hello world", "")` | `[]` —— 没 query 不可能命中 |
| `test_highlights_match` | `extract_snippets("LanceDB is zero-dependency", "LanceDB")` | 至少一条片段,且片段里有 `**LanceDB**`(双星号是高亮标记)|
| `test_no_match_returns_empty` | `extract_snippets("hello world", "lambda")` | `[]` |

## 覆盖的代码路径

- `util/snippet.py::extract_snippets()` 主流程
- 高亮包裹用 markdown 加粗(`**...**`),消费方(/v2/search 响应)直接渲染

## 为什么不验完整片段字符串

`extract_snippets` 内部会做窗口截断、合并相邻命中等启发式 —— 全字符串断言会把
启发式实现细节硬编码进测试,改逻辑就大批量失败。验"高亮标记存在"已经能盯死
**契约**(命中 → 输出标记)。
