# Hook 安装 pipeline

`memory.talk setup` 的 7-step pipeline 怎么在每个 host AI CLI(Claude Code / Codex / …)装 `memory.talk recall hook` 进 plugin,以及 drift detection、force reinstall 的设计。

相关:
- CLI: [`../../cli/v3/setup.md`](../../cli/v3/setup.md)
- Codex 专属 trust 流程: [codex-trust-flow.md](codex-trust-flow.md)
- Session ID 命名(为什么 hook 需要 `--source`): [session-namespace.md](session-namespace.md)

## Pipeline 结构

setup 是固定 step 流水线:

```
embedding → storage → server config → sync → persist → server proc → hooks
```

**每次跑都把全部 step 跑一遍**,不论 settings.json 有没有变。每个 step 自己幂等,自己决定要不要动。这是**结构上防御**:`for step in STEPS` 循环,没有早 return 路径,任何新加 step 都不能被跳过(0.8.5 的 hook step 被跳过 bug 就是被这个结构防住的)。

| # | step | 收集字段 | 副作用 |
|---|---|---|---|
| 1 | embedding | `embedding.*` | 调真实 endpoint 验证 |
| 2 | storage | `vector.provider` `relation.provider` | — |
| 3 | server config | `server.port` | — |
| 4 | sync | `sync.enabled` | — |
| 5 | persist | — | atomic write `settings.json` |
| 6 | server proc | — | 启动 / 重启后台守护 |
| 7 | hooks | — | 装 / 卸 host AI CLI 的 recall hook |

## Step 7:Hooks step

**每个探测到的 host AI CLI 问一个 Y/n**。Y → 装 / 保持,N → 卸载。默认 Y。

```
Claude Code v2.1.157 — not installed
? install hook? (Y/n)

Codex v0.133.0 — installed, awaiting TUI trust
? keep hook installed? (Y/n)
```

每行三件事:host 名 + 版本 + 当前状态。状态从 `current_state(materialized_dir)` 计算,包含 `absent` / `installed` / `installed-verified` / `installed-drift` / `installed-disabled` / `installed-failed` / `installed-untrusted`(只 Codex)。

### Y 路径:install

1. 把 wheel 内 `hook_assets/<host>/` 实体化到 `~/.memory.talk/hook_plugins/<host>/`(hash 比对,无变化则 skip copy)
2. **若内容变了且 host 已装** → 强制 `plugin remove` + `plugin add` 推新内容进 host 缓存(见下方 § Force reinstall)
3. 否则调 host CLI 装 plugin(`claude plugin install` / `codex plugin add`)
4. **Codex 专属**:trust 步,详见 [codex-trust-flow.md](codex-trust-flow.md)
5. 跑 probe:host CLI exec 一个 magic token,hook 收到后写 sentinel 文件,setup 看 sentinel → 确认 hook 真 fire 了
6. probe 通过 → 写 `hook_state.json` 记 `last_verified_at`

### N 路径:uninstall

1. 调 host CLI 卸 plugin
2. 删 `~/.memory.talk/hook_plugins/<host>/`
3. 清 `hook_state.json` 对应 host 条目

## Force reinstall on content drift

**问题**:host CLI(Codex / Claude Code)copy plugin files into their own cache at `plugin add` 时,以后**不再 re-read 我们的 marketplace 目录**。`marketplace upgrade` 只在 plugin manifest 的 `version` 字段 bump 时 re-pull。

我们不可靠地在每次发版 bump version(版本是 wheel 级别的,跟 plugin manifest 不一一对应)。所以**改 hook command 的发版,host CLI 的 plugin cache 仍然是旧版**。

**修复**:`_apply_install` 检测到 `materialize()` 写了新内容(`changed=True`)且 plugin 已在 host cache(`state != ABSENT`)→ 主动 `uninstall + install` 强制刷:

```python
changed = hook_materialize.materialize(adapter.asset_subdir, r.materialized)
if changed and r.state != HostState.ABSENT:
    err_console.print("  · content changed — forcing reinstall to refresh host plugin cache")
    adapter.uninstall()
adapter.install(r.materialized)
```

Codex 这条路径会触发 trust hash 失效 → 用户需重走 trust 步,但内容变了 trust hash 本来就要重算,所以这个代价**不可避免**(详见 [codex-trust-flow.md](codex-trust-flow.md))。

## Adapter 注册表

每个 host 是一个 `HostAdapter`:

```python
class HostAdapter:
    name: str                  # 'claude-code' / 'codex' / ...
    display_name: str
    asset_subdir: str          # hook_assets/<asset_subdir>/

    def detect() -> HostPresence | None: ...
    def current_state(materialized) -> HostState: ...
    def install(materialized) -> None: ...
    def uninstall() -> None: ...
    def trust_ok() -> bool: ...                  # Codex 用
    def probe_command(token) -> list[str]: ...
```

注册表 `ADAPTERS: list[HostAdapter]`,加新 host = 加一个 adapter 类 + 一个 `hook_assets/<新 host>/` 子目录。Setup wizard 主流程**完全不动**。

## 非 TTY 跳过

管道、CI、`runner.invoke` 测试:整个 hooks step 跳过,summary 标 `skipped: non-interactive shell`。

理由:hooks step 可能要交互确认 trust loop(Codex),在没法交互的 shell 里默默 install 会留半截脏数据。**宁可什么也不做也不留惊喜**。

## 不可变契约

- 每次 setup 跑完,**所有 7 个 step 都执行了**。没有"配置没变所以跳过后面"的早 return 路径。
- 每个有副作用的 step 要么**完成**要么**回滚到入口状态**。绝不允许"做了一半 return 一个状态字典就走"(0.8.8 dirty-state bug 就是违反这条)。
- settings.json 写入是原子(tmp + rename),Ctrl-C 不会留半个 JSON。
- 已存在的目录 / 文件 / 数据**不动** —— sessions / cards / events.jsonl / search_log 永远不被 setup 触碰。
