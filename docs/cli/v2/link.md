# link

v2 里 link 只有 create。查询与删除都不开放——link 的存在应该随 `view` 的 response 一起返回（嵌在被读取对象的 `links` 字段里），而 TTL 会随读取隐式刷新。

Link 分两种：

- **默认 link**：写 card 时从 `rounds` 里出现的每个 `session_id` 自动生成一条 card → session 关联。`ttl = 0`，生死跟随 card（card 活它就活，card 被遗忘它一起遗忘），不能被独立续命。写入者无需也无法传入。
- **用户 link**：通过 `link create` 写入。有独立 TTL（默认 100），可被 view 隐式续命，也会独立过期。

## link create

```bash
memory-talk link create '<json>'
```

输入 JSON：

```json
{
  "source": "sch_01K7XABC....c1",
  "target": "sch_01K7XABC....s2",
  "comment": "选型之后踩的坑"
}
```

- `source` / `target` **只接受 `result_id`**——必须先 `search` 拿到结果，再在它们之间建 link。裸 `card_id` / `session_id` 一律不接受。
  - 可接受的 result_id 形态：`.c<N>`（card）、`.s<N>`（session）、以及 view 响应里现生的 `.l<N>`（继续追某条 link 的对端）。
  - 这是刻意的设计：v2 里"引用一个对象"永远要经过 search 走一遭，服务端借此追踪 link 从何而来。刚写完一张 card / 刚 sync 完一个 session 不会马上就建 link——那样也没有被 search 触达的语义。
- `comment` 可选。

支持的类型组合（方向由 source → target 表达，双向都允许）：

| source | target |
|--------|--------|
| card | card |
| card | session |
| session | card |
| session | session |

禁止 `source == target`（自环，两个 result_id 解析到同一个对象时也算）。

输出：

```json
{"status": "ok", "link_id": "01jzq7rm...", "ttl": 1209600}
```

返回的 `link_id` **不用于**后续读取或删除——v2 不再暴露这类管理路径。它保留只是为了在日志 / 调试里定位这条 link。

## 错误

| 情况 | 错误 |
|------|------|
| `source` 或 `target` 不是 result_id（裸 `card:xxx` / `session:xxx` / 任何其它前缀） | 400，`source/target must be a result_id` |
| result_id 已过期（超出 `settings.search.result_ttl`） | 400，`expired` |
| result_id 未知 / 无法解析 | 404 |
| result_id 指向 `.l<N>` 但底层 link 已过期 | 按对端解析失败处理，`expired` |
| `source` 和 `target` 解析到同一个对象（自环） | 400，`self-loop not allowed` |
| 类型组合不在支持表内 | 400，`unsupported link type: <source_type> -> <target_type>` |
| `comment` 超长（见 settings 里的上限） | 400，`comment too long` |
