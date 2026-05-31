# setup

```bash
memory.talk setup
```

**纯交互式**幂等 wizard。无参数,无 `--json`。同一条命令覆盖首次安装和重配置。

数据根固定 `~/.memory.talk`,不暴露 `--data-root`。

---

## Pipeline 总览

setup 是一条**固定 step 流水线**:

```
embedding → storage → server config → sync → persist → server proc → hooks
```

**每次跑都把全部 step 跑一遍**,不论 settings.json 有没有变。每个 step 自己幂等,自己决定要不要动。这是结构上防御 — wizard 用 `for step in STEPS` 循环,不能被早 return 跳过任何 step(0.8.5 的 hook step 被跳过 bug 就是被这个结构防住的)。

| # | step | banner | 收集字段 | 副作用 |
|---|---|---|---|---|
| 1 | embedding | `── Embedding ──` | `embedding.*` | 调真实 endpoint 验证 |
| 2 | storage | `── Storage ──` | `vector.provider` `relation.provider` | — |
| 3 | server config | `── Server ──` | `server.port` | — |
| 4 | sync | `── Sync ──` | `sync.enabled` | — |
| 5 | persist | (silent) | — | atomic write `settings.json` |
| 6 | server proc | (silent) | — | 启动 / 重启后台守护 |
| 7 | hooks | `── Recall hooks ──` | — | 装 / 卸 host AI CLI 的 recall hook |

---

## 每个 step 详细

### 1. Embedding

收集:`provider`(`local` / `openai`)→ `model` → `dim` → 若 `openai` 再问 `endpoint` / `auth_key`。

**写入前必须探测通过** —— 同步 HTTP 打一次目标 endpoint 验证 key + dim 对得上。

| 情况 | 行为 |
|---|---|
| 探测成功 | 打 `✓ embedding verified`,继续 |
| 探测失败 | 抛 `ConfigValidationError` → wizard 整个 exit 1,**settings.json 没写**(世界回到 setup 之前) |

**幂等**:修改模式下每个 prompt 的默认值 = 现有值,Enter 全 keep 等于不变。

> 已知缺口:探测失败现在是直接退出,**不循环让用户重填**。理想行为应该像 `4. sync` 那样可以重试。当前是 step 1 一旦填错,要从头跑 setup。

### 2. Storage

收集:`vector.provider`(只有 `lancedb`)+ `relation.provider`(只有 `sqlite`)。

单选项仍然 prompt,把"这是一个可配置层"显式化 —— 后续加 pgvector / Pinecone 等不需要改 onboarding 姿势。

无副作用,纯收集。

### 3. Server config

收集:`server.port`(默认 7788,校验 1-65535)。

不动 server 进程。只收集。

### 4. Sync

先打印探测到的 sync source(`Detected sources: ✓ claude-code → ~/.claude/projects` 等),让用户知道开启 sync 后哪些会被自动 ingest。

然后:`Enable backend sync? (Y/n)`。

只收集 flag,不动 SyncWatcher 运行时。

### 5. Persist(无 banner)

把前 4 步收集到的 owned 字段 diff against `base`(磁盘上的现有 settings.json):

| 情况 | 行为 |
|---|---|
| 有 diff | 原子写(tmp + rename)`settings.json`,invalidate `Config` 缓存 |
| 无 diff | 打 dim `settings.json unchanged`,不写文件 |

`Settings` 默认值 **不会** 被 materialize 到磁盘上 —— wizard 只写它实际 prompt 过的字段,用户自己加的 `search.*` / `recall.*` 等不在 owned 集合里的字段完全不动。这样 schema 默认值变化(如 0.8.2 改 ranking_formula default)能在下次 load 时透传。

无论写没写,都跑 `cfg.ensure_dirs()` 补齐 `sessions/ cards/ vectors/ logs/search/` 等数据目录。

### 6. Server proc(无 banner)

| 情况 | 行为 |
|---|---|
| 首次安装 | 问 "Start the server now? (Y/n)",Y → 启动 |
| 修改模式 + persist 写了文件 + server 在跑 | 问 "Restart server? (Y/n)",Y → stop + start |
| 其它 | 不动 |

"server 在跑" 判定是三重:`pid_path` 存在 + `pid_alive(pid)` + HTTP 探针返回 → 防止 PID 回收骗到我们去 SIGTERM 别人。

### 7. Recall hooks

**每个探测到的 host AI CLI(Claude Code / Codex / …)问一个 Y/n**。Y → 装 / 保持,N → 卸载。默认 Y。

```
Claude Code v2.1.157 — not installed
? install hook? (Y/n)

Codex v0.133.0 — installed, awaiting TUI trust
? keep hook installed? (Y/n)
```

每行三件事:host 名 + 版本 + 当前状态。状态从 `current_state(materialized_dir)` 计算,包含 `absent` / `installed` / `installed-verified` / `installed-drift` / `installed-disabled` / `installed-failed` / `installed-untrusted`(只 Codex)。

**Y 路径**(install):
1. 把 wheel 内 `hook_assets/<host>/` 实体化到 `~/.memory.talk/hook_plugins/<host>/`(hash 比对,无变化则 skip copy)
2. 调 host CLI 装 plugin(`claude plugin install` / `codex plugin add`)
3. **Codex 专属:trust 步**(下方详细)
4. 跑 probe:host CLI exec 一个 magic token,hook 收到后写 sentinel 文件,setup 看 sentinel → 确认 hook 真 fire 了
5. probe 通过 → 写 `hook_state.json` 记 `last_verified_at`

**N 路径**(uninstall):
1. 调 host CLI 卸 plugin
2. 删 `~/.memory.talk/hook_plugins/<host>/`
3. 清 `hook_state.json` 对应 host 条目

**Codex trust 步**(只 Codex,因为 Codex 设计要求 per-hook trust):
- 装完后读 `~/.codex/config.toml` `[hooks.state]` 找匹配 `trusted_hash`
- 有 → done
- 没有 → 循环:打一行短指令 + 等用户 Enter 重检 + Ctrl-C 放弃
- 用户放弃 → **回滚**(`codex plugin remove` + 删 materialized + 清 hook_state) → 世界回到 step 入口前。summary 标 `codex=aborted-trust-rolled-back`

**非 TTY shell**(管道、CI、`runner.invoke` 测试):整步跳过,summary 标 `skipped: non-interactive shell`。不在没法交互的环境里默默 install 留下惊喜。

---

## 不可变契约

- 每次 setup 跑完,**所有 7 个 step 都执行了**。没有"配置没变所以跳过后面"的早 return 路径。
- 每个有副作用的 step 要么**完成**要么**回滚到入口状态**。绝不允许"做了一半 return 一个状态字典就走"。
- settings.json 写入是原子(tmp + rename),Ctrl-C 不会留半个 JSON。
- 已存在的目录 / 文件 / 数据**不动** —— sessions / cards / events.jsonl / search_log 永远不被 setup 触碰。

---

## 输出(stdout · raw markdown)

wizard 的 prompt 文字 + 用户输入回显走 **stderr**,跑完最终摘要走 **stdout**:

````markdown
# setup · **ok**

| field | value |
|---|---|
| data_root | `/home/user/.memory.talk` |
| settings | `/home/user/.memory.talk/settings.json` |
| changed | 4 fields (embedding.model, embedding.dim, server.port, sync.enabled) |
| server | restarted · pid 12345 · port 7788 |
| hooks | claude-code=verified, codex=verified |
| notice | **embedding dim changed** — re-embed all cards via `memory.talk setup` once card writes are implemented |
````

- `changed` 没变化时:`nothing — config unchanged`
- `server` 没动时:`(unchanged)`
- `hooks` 在 non-TTY 跳过时:`skipped — non-interactive shell`
- `notice` 行只在 embedding `dim` 变了时出现(提示后续需重算向量,**当前还没实现自动重算**)

---

## 错误与异常路径

| 触发 | 行为 |
|---|---|
| `~/.memory.talk` 是文件而不是目录 | exit 1 |
| `settings.json` 损坏 JSON | 询问"备份成 `.bak` 重来吗"(默认 Y);N → exit 1 |
| embedding probe 失败(401 / DNS / dim 不匹配) | exit 1,settings 没写。**目前不重试** —— 重跑 setup 是当前的"修复"姿势 |
| 任一 step 中 Ctrl-C | exit 130(SIGINT 标准),settings 没写 |
| Codex trust 用户主动放弃(Ctrl-C in trust loop) | 回滚 plugin install,step 标 `aborted-trust-rolled-back`,其它 step 不受影响,setup 整体仍 exit 0 |
| probe 通过但 sentinel 没出现 | hook step 该 host 标 `installed-unverified`,setup 整体仍 exit 0,提示用户手动测一次 |

---

## 副作用清单

setup 会改的:

- `~/.memory.talk/settings.json`(atomic)
- `~/.memory.talk/{sessions,cards,vectors,logs/search}/`(只补缺失)
- `~/.memory.talk/hook_plugins/<host>/`(每个 host 一套实体化的 plugin 资源)
- `~/.memory.talk/hook_state.json`(verify 时间戳缓存,不是真相源)
- server daemon(start / restart / no-op)
- **通过 host CLI** 间接改:
  - `~/.claude/settings.json`:`enabledPlugins` + `extraKnownMarketplaces` 加 `memory-talk-recall@memory-talk` + `memory-talk` 条目
  - `~/.codex/config.toml`:`[marketplaces.memory-talk]` + `[plugins."memory-talk-recall@memory-talk"]` + `[hooks.state.*]`(trust hash,由用户在 TUI 操作产生)

setup 永远不动:

- `sessions/` / `cards/` / `events.jsonl` / `search_log`
- 用户在 settings.json 里手写的非 owned 字段(`search.*`、`recall.*`、`explore.*`、`embedding.batch_size` 等)
- 用户在 `~/.claude/settings.json` / `~/.codex/config.toml` 手写的其它 marketplace / plugin / hook

---

## 跟其它命令的边界

- `memory.talk server start` 是 setup 的子集 —— setup 是它的超集,把 wizard + 配置 + 启动捆在一条命令里。两条路最终落地是同一份 settings.json。
- `memory.talk sync` 跟 setup 解耦 —— setup 跑完后由用户自己决定何时第一次 sync。
- 卸载 hook 不另开命令,就是再跑 setup 在 hooks step 答 N。

---

## 推荐姿势

```bash
# 首次安装
memory.talk setup

# 改 embedding 或加新装的 host CLI 的 hook
memory.talk setup     # 全部 step 走一遍,改要改的,其他 Enter 保持

# 排查问题(看一眼当前 server 状态)
memory.talk server status
```
