# Card 删除流程

`DELETE /v3/cards/{card_id}` / `memory.talk card delete` 的服务端清理顺序、级联策略、不级联的对象。

相关:
- CLI: [`../../cli/v3/card.md`](../../cli/v3/card.md) (`card delete`)
- API 字段表: [`../../api/v3/cards.md`](../../api/v3/cards.md)

## 删除顺序

```
1. 查 card 存在性 → 不存在返 404
2. 算 inbound_refs(其他 card 通过 source_cards 引用 this 的数量,只为响应展示)
3. 删 reviews(WHERE card_id = ?,单 SQL)
4. 删 SQLite 行(原子事务):
   - card_source_cards WHERE card_id = ?    (outbound)
   - card_stats WHERE card_id = ?
   - cards WHERE card_id = ?
5. 删 LanceDB cards 行(best-effort,失败 log warning)
6. rmtree cards/<bucket>/<card_id>/ 整目录(best-effort,失败 log warning)
```

**SQLite 一次事务**;vector/file 失败不回滚 SQLite。

## 顺序为什么这样

| 阶段 | 失败 | 回滚 SQLite 删除? |
|---|---|---|
| SQLite tx | 失败 | tx 整体回滚,API 返 500 |
| vector delete | 失败 | **不回滚** —— log warning,card 仍算已删,orphan vector 由 search-time `card_row is None` 检查过滤 |
| file rmtree | 失败 | **不回滚** —— log warning,orphan dir 不影响查询(无 read path 扫这些) |

为什么 vector/file 失败不回滚 SQLite:**用户视角已删**。把 SQLite 删除回滚成"看起来还在"反而是更差的状态 —— 用户以为没删,但 vector/file 状态错乱。一致性的方向是**前进,不是后退**。Orphan vector/file 由未来 rebuild 命令清。

## 删什么 / 不删什么

| 对象 | 删 | 不删 | 理由 |
|---|---|---|---|
| `cards.card_id` 行 | ✅ | | 主要 |
| `card_stats` 行 | ✅ | | 跟 card 1:1,孤儿无意义 |
| `card_source_cards` outbound(this card 引用别人的) | ✅ | | this 没了,它的 outbound refs 无意义 |
| `card_source_cards` inbound(别人引用 this 的) | | ❌ | **不级联** —— 别人删自己得别人自己决定 |
| `reviews` 上 `card_id=this` 的所有 review | ✅ | | review 依附于 card |
| LanceDB `cards` 表 vector | ✅ | | 否则搜索会持续返回幽灵命中 |
| `cards/<bucket>/<card_id>/` 整个目录 | ✅ | | card.json + events.jsonl + reviews.jsonl + tags.json 都属于这个 card |
| `recall_event` 里 `returned_ids[]` / `skipped_ids[]` 包含 this card_id | | ❌ | recall_event 是**历史记录**,删 card 不改写 history。`recall read` 显示 card_id,但 insight 是 `(card no longer exists)` |
| `sessions/<source>/<sid>/rounds.jsonl` 里的源 round | | ❌ | card 引用 round,不拥有它;删 card 不动 session |
| `card.events.jsonl` 里的历史 events | ✅(随目录删) | | 没办法不删,目录都没了 |

## inbound refs 不级联的设计选择

被这张 card 引用的关系:`card_x.source_cards[].card_id = card_this`,反向查 `card_source_cards.source_card_id = card_this`。

DELETE 不级联删除 card_x,因为:

1. **级联是单向慢病**:级联删一张 card 可能触发删 10 张,删 10 张可能再级联 100 张。用户看到的是"我只删了一张" → 实际灾难性。
2. **dangling 引用是**可恢复**的**:card_x 仍然存在,只是它的 source_cards[] 里有个 ID 现在指不到对象。read card_x 时 API 可以显示"(referenced card not found)" 而不报错。
3. **响应里把数字说出来**:`inbound_refs_dangling: N` 直接告诉用户"你删的这张被 N 张引用"。用户自己决定是不是要补救(比如新建一张取代它)。

## 不是 idempotent

第二次 DELETE 同一个已删除的 card → 404(不静默 no-op)。理由:

- 调用方不应该重复调用我们;**重复调用是 bug 信号**,我们应该 surface 它而不是吞掉
- HTTP DELETE 的 idempotency 是"重复执行不产生额外 side effect",而不是"第二次返回 200"。返回 404 满足前者(没有副作用)同时给调用方知情权
- 反过来"第二次返 200" 让客户端无法区分"我刚删的" vs "本来就不存在",引入 bug

## Code 位置

- 服务: `memorytalk/service/cards.py:CardService.delete`
- API: `memorytalk/api/cards.py:delete_card`
- CLI: `memorytalk/cli/card.py:delete`
- Storage rmtree: `memorytalk/provider/storage.py:LocalStorage.delete_prefix`
