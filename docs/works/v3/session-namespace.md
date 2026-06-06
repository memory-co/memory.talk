# Session ID 命名空间

`session_id` 的 canonical 格式 + 怎么从平台原始 id 算出来 + 为什么 recall hook 必须传 `--source`。

相关:
- Structure: [`../../structure/v3/session.md`](../../structure/v3/session.md), [`../../structure/v3/recall.md`](../../structure/v3/recall.md)
- 代码: `memorytalk/adapters/base.py:BaseAdapter.mint_session_id`

## Canonical 格式

```
session_id = f"sess-{loc_code}-{tail}"

  loc_code = sha256(f"{source_name}#{location}").hexdigest()[:8]
  tail     = upstream_id.rsplit("-", 1)[1]    # UUID 最后一段
```

算 canonical 要 **3 件输入**:

| 输入 | 例子 | 谁知道 |
|---|---|---|
| `source_name` | `claude-code`, `codex`, `openclaw` | 装 hook 的 plugin / sync 配置 |
| `location` | `/Users/zzz/.claude/projects` | 同上 |
| `upstream_id` | `187c6576-875f-4e3e-8fd8-f21fe60190b0` | hook payload / 平台 session 文件名 |

`tail` 取 UUID 最后一段是为了让 canonical 短一些(~22 chars)还能保留人眼可辨认的尾巴。`loc_code` 把 `(source, location)` 折叠成 8 char,跨 endpoint 防 id 碰撞。

历史上有过更长的 `sess_<full-uuid>` 形态(0.7.x 之前),`parse_id` 仍接受作为 read 兼容,但**新 mint 永远产出 `sess-` 前缀的新格式**。

## hook 必须传 `--source`

只有 `upstream_id` 在 hook payload 里。`source_name` 和 `location` 属于"装这个 hook 的 host CLI 是谁、它的 session 文件在哪",**hook 服务端不知道,必须由 plugin 显式声明**:

```bash
# Claude Code 装的 plugin 调:
memory.talk recall hook --source claude-code --location ~/.claude/projects

# Codex 装的 plugin 调:
memory.talk recall hook --source codex --location ~/.codex/sessions
```

`--location` 可选,缺省走 adapter 的 `DEFAULT_LOCATION`,够覆盖单 endpoint 场景。多 endpoint 用户(同 source 装在多个路径)需要手动传。

setup wizard 在实体化每个 host 的 plugin 时,把对应 `--source X` 写进 plugin 的 `hooks.json` 的 command 字符串 —— 不同 host 装的 plugin 拿到的 command 自然就不同。详见 [hook-installation.md](hook-installation.md)。

## 为什么不靠 hook 服务端"猜" source

历史上 `util/ids.py:prefix_session_id` 干过这事 —— **写死 `ClaudeCodeAdapter` + `DEFAULT_LOCATION`** 然后调 `mint_session_id`。后果:

| Hook 来源 | recall 算出的 session_id | sessions 表里 sync 写的 session_id | 对得上? |
|---|---|---|---|
| Claude Code(默认位置) | `sess-{cc_loc}-{tail}` | 同 | ✅ |
| Claude Code(自定义位置) | `sess-{cc_DEFAULT_loc}-{tail}`(错) | `sess-{cc_actual_loc}-{tail}` | ❌ |
| **Codex** | `sess-{cc_loc}-{tail}`(完全错) | `sess-{codex_loc}-{tail}` | ❌ |

**0.8.x Codex 的 recall_log 跟 sync 后 sessions 表是完全两个 namespace,join 不上。** 这个 bug 一直没显形,因为旧设计也没有"join recall 跟 sessions"的视图 —— 直到 0.9.0 `recall list` / `recall read` 要按 session 聚合才暴露。

0.9.0 修这个 bug 的代价:`util/ids.py:prefix_session_id` 这个 legacy 函数从 recall 路径删除,recall 服务接 `(--source, --location, raw_uuid)` 三参数,经 `BaseAdapter.mint_session_id` 算 canonical。

## 不验证 session 在 sessions 表里存在

recall 是**实时** hook,sync 是**异步定时**。常见时序:

```
[hook 1]  POST /v3/recall {session_id: sess-<loc>-<tail>, prompt: ...}    ← 写 recall_event
[hook 2]  POST /v3/recall {session_id: sess-<loc>-<tail>, prompt: ...}    ← 写 recall_event
[hook 3]  POST /v3/recall {session_id: sess-<loc>-<tail>, prompt: ...}    ← 写 recall_event
[sync]    定时器跑 → 把这个 session 落到 sessions 表                       ← 现在才有 session 实体
```

写入路径 **不**查 sessions 表存在性,**不**加外键约束。等 sync 落地,recall_event 的 session_id 跟 sessions.session_id 同形,关联自然成立,**不需 backfill**。

同样的考虑也适用于 review:`review.session_id` 可以指向尚未 sync 进来的 session,因为 review 创建时间可能领先于 sync(罕见但合法)。
