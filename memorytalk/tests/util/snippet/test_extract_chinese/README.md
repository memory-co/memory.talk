# test_extract_chinese

`extract_snippets()` 的中文路径 —— 中文 query 走 jieba 分词后再做命中匹配。

## 场景矩阵

| 测试函数 | 输入 | 预期 |
|---|---|---|
| `test_handles_chinese_via_jieba` | `text="讨论 LanceDB 向量存储的选型理由"`,`query="LanceDB 选型"` | 至少一条片段含 `**`(jieba 拆出的某个 token 被高亮)|

## 覆盖的代码路径

- `util/snippet.py` 中 jieba 分词分支
- 中文 query 不会走"整串等值匹配",而是切成 token 列表分别命中

## 为什么只验"含双星号"

jieba 分词结果跟字典版本耦合,断言具体哪些 token 命中会变成"jieba 升级就坏的
脆性测试"。验"至少高亮了一个 token"足以盯死契约 —— 中文 query 必须能产出片段。

## 为什么单独立目录

中文路径触发 jieba 加载(冷启动稍慢),拆开看是为了**语义清晰**:有人去掉
jieba 依赖时,基础测试还能跑,中文这一组会单独红。
