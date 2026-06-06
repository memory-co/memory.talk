# setup

```bash
memory.talk setup
```

**纯交互式**幂等 wizard。无参数,无 `--json`。同一条命令覆盖首次安装和重配置。

数据根固定 `~/.memory.talk`,不暴露 `--data-root`。

Pipeline 机制 / hook 安装内部流程 / Codex trust 流程见 [`../../works/v3/hook-installation.md`](../../works/v3/hook-installation.md) 和 [`../../works/v3/codex-trust-flow.md`](../../works/v3/codex-trust-flow.md)。

---

## Step 概览

```
embedding → storage → server config → sync → persist → server proc → hooks
```

每次跑都把全部 step 跑一遍,不论 settings.json 有没有变。每个 step 自己幂等。

| # | step | banner | 收集字段 |
|---|---|---|---|
| 1 | embedding | `── Embedding ──` | `embedding.*` |
| 2 | storage | `── Storage ──` | `vector.provider` / `relation.provider` |
| 3 | server config | `── Server ──` | `server.port` |
| 4 | sync | `── Sync ──` | `sync.enabled` |
| 5 | persist | (silent) | 原子写 `settings.json` |
| 6 | server proc | (silent) | 启动 / 重启后台守护 |
| 7 | hooks | `── Recall hooks ──` | 装 / 卸 host AI CLI 的 recall hook |

---

## 各 step 用户视角

### 1. Embedding

prompt:`provider`(`local` / `openai`)→ `model` → `dim` → 若 `openai` 再问 `endpoint` / `auth_key`。

**写入前同步调真实 endpoint 验证**。失败 → wizard exit 1,settings.json 没写。

幂等:修改模式下默认值 = 现有值,Enter 全 keep 等于不变。

### 2. Storage

prompt:`vector.provider`(只有 `lancedb`)+ `relation.provider`(只有 `sqlite`)。

无副作用,纯收集。

### 3. Server config

prompt:`server.port`(默认 7788,校验 1-65535)。

不动 server 进程。只收集。

### 4. Sync

先打印探测到的 sync source(`Detected sources: ✓ claude-code → ~/.claude/projects` 等),然后:`Enable backend sync? (Y/n)`。

只收集 flag,不动 SyncWatcher 运行时。

### 5. Persist(无 banner)

diff 前 4 步收集到的 owned 字段 vs 现有 settings.json。

| 情况 | 行为 |
|---|---|
| 有 diff | 原子写(tmp + rename)`settings.json` |
| 无 diff | 打 dim `settings.json unchanged`,不写文件 |

`Settings` 默认值**不会**被 materialize 到磁盘上 —— wizard 只写它实际 prompt 过的字段。

无论写没写,都跑 `cfg.ensure_dirs()` 补齐 `sessions/ cards/ vectors/ logs/search/` 等数据目录。

### 6. Server proc(无 banner)

| 情况 | 行为 |
|---|---|
| 首次安装 | 问 "Start the server now? (Y/n)",Y → 启动 |
| 修改模式 + persist 写了文件 + server 在跑 | 问 "Restart server? (Y/n)" |
| 其它 | 不动 |

### 7. Recall hooks

每个探测到的 host AI CLI 问一个 Y/n:

```
Claude Code v2.1.157 — not installed
? install hook? (Y/n)

Codex v0.133.0 — installed, awaiting TUI trust
? keep hook installed? (Y/n)
```

Y 路径装 plugin + verify probe;N 路径卸 plugin。Codex 多一步 trust(详见 [codex-trust-flow.md](../../works/v3/codex-trust-flow.md))。

**非 TTY shell**(管道、CI、`runner.invoke` 测试):整步跳过,summary 标 `skipped: non-interactive shell`。

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

---

## 错误与异常路径

| 触发 | 行为 |
|---|---|
| `~/.memory.talk` 是文件而不是目录 | exit 1 |
| `settings.json` 损坏 JSON | 询问"备份成 `.bak` 重来吗"(默认 Y);N → exit 1 |
| embedding probe 失败 | exit 1,settings 没写。重跑 setup 是当前的"修复"姿势 |
| 任一 step 中 Ctrl-C | exit 130(SIGINT 标准),settings 没写 |
| Codex trust 用户主动放弃 | 回滚 plugin install,step 标 `aborted-trust-rolled-back`,其它 step 不受影响,setup 整体仍 exit 0 |
| probe 通过但 sentinel 没出现 | hook step 该 host 标 `installed-unverified`,setup 整体仍 exit 0 |

---

## 推荐姿势

```bash
# 首次安装
memory.talk setup

# 改 embedding 或加新装的 host CLI 的 hook
memory.talk setup     # 全部 step 走一遍,改要改的,其他 Enter 保持

# 排查问题
memory.talk server status
```
