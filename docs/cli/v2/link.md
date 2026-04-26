# link

v2 里 link 只有 create。查询与删除都不开放——link 的存在随 `view` 的 response 一起返回(嵌在被读取对象的 `links` 字段里),TTL 随 view 隐式刷新。

Link 分两种:

- **默认 link**:写 card 时从 `rounds` 里出现的每个 `session_id` 自动生成一条 card → session 关联。`ttl = 0`,生死跟随 card(card 活它就活,card 被遗忘它一起遗忘),不能被独立续命。写入者无需也无法传入。
- **用户 link**:通过 `link create` 写入。有独立 TTL(默认 1209600 秒 = 14 天),可被 view 隐式续命,也会独立过期。

## link create

```bash
memory-talk link create '<json>' [--json]
```

输入 JSON:

```json
{
  "source_id": "card_01jz8k2m",
  "source_type": "card",
  "target_id": "sess_187c6576",
  "target_type": "session",
  "comment": "选型之后踩的坑"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `source_id` | 是 | 源对象带前缀 id(`card_<...>` 或 `sess_<...>`) |
| `source_type` | 是 | `card` 或 `session`(冗余但方便 dispatch,服务端会校验和 id 前缀一致) |
| `target_id` | 是 | 目标对象带前缀 id |
| `target_type` | 是 | `card` 或 `session` |
| `comment` | 否 | 说明为什么关联 |

支持的类型组合(方向由 source → target 表达,双向都允许):

| source | target |
|--------|--------|
| card | card |
| card | session |
| session | card |
| session | session |

禁止 `source == target`(自环)。

## 输出

### Markdown(默认)

````markdown
ok: linked `card_01jz8k2m` → `sess_187c6576` · ttl 14d
````

错误:

````markdown
**error:** self-loop not allowed
````

### JSON(`--json`)

```json
{"status": "ok", "link_id": "link_01jzq7rm", "ttl": 1209600}
```

```json
{"error": "self-loop not allowed"}
```

- `ttl` = 写入时刻的 `settings.ttl.link.initial`(默认 1209600 秒 = 14 天)。
- 返回的 `link_id` **不用于**后续读取或删除——v2 不暴露 link 的直接管理路径。它主要用于日志 / 调试里定位,以及作为 log 事件的 `link_id` 字段出现。

## 错误

| 情况 | 状态 |
|------|------|
| `source_id` / `target_id` 前缀非法(非 `card_` / `sess_`) | 400,`invalid id prefix` |
| `source_type` 和 `source_id` 前缀不一致 | 400,`type mismatch` |
| 对象不存在 | 404 |
| `source_id == target_id`(自环) | 400,`self-loop not allowed` |
| `comment` 超过 `settings.search.comment_max_length` | 400,`comment too long` |
