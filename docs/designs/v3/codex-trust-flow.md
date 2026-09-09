# Codex trust 流程

Codex 的 plugin 必须 user-side trust 才能让 hook fire。memory.talk setup 怎么引导这一步、检测 trust 是否生效、用户放弃时怎么回滚。

相关:
- 整体 hook 安装: [hook-installation.md](hook-installation.md)
- CLI: [`../../cli/v3/setup.md`](../../cli/v3/setup.md)

## 为什么 Codex 要 trust

Codex 在 `~/.codex/config.toml` 的 `[hooks.state]` 里维护每条已装 hook 的**信任哈希**:

```toml
[hooks.state."memory-talk-recall.plugin.hook"]
trusted_hash = "sha256:abc123..."
```

只有 trusted_hash 跟当前 hook 内容算出来的 sha256 完全一致,Codex 才允许这个 hook 真的执行。换 hook 内容 → hash 变 → 旧 trust 失效 → 用户必须重新在 TUI 里按 `t` 信任。

这是 Codex 的安全设计,不是我们的选择,**只能配合**。

## Trust loop

setup 装完 plugin 后,如果 `adapter.trust_ok()` 返 False:

```
1. 打一行短指令(yellow ⚠):
     "Codex hook needs trust. Open `codex`, then in TUI type `t` to accept."
2. 等用户按 Enter 重检
3. trust_ok() 是 True → done
4. trust_ok() 仍是 False → 回到第 2 步
5. 用户按 Ctrl-C → 触发 rollback(下方)
```

**循环直到通过或用户主动放弃**。模型类似 embedding probe 的 "fail loud and keep asking"。

## 用户放弃 → rollback

如果用户在 trust loop 里 Ctrl-C(`KeyboardInterrupt`),setup **不留半截**:

```python
adapter.uninstall()             # codex plugin remove memory-talk-recall@memory-talk
shutil.rmtree(materialized_dir) # 删 ~/.memory.talk/hook_plugins/codex/
hook_state.clear(adapter)        # 清 hook_state.json 对应条目
```

回滚之后世界回到"setup 进 hooks step 入口前"的状态:

- ~/.codex/config.toml 没有这个 plugin
- 我们的 materialized 目录没了
- hook_state.json 不再标这个 host 为 active

summary 标 `codex=aborted-trust-rolled-back`,其它 step 继续。setup 整体仍 exit 0。

## 为什么 rollback 必须

不 rollback 的代价:Codex 那边留着 plugin 注册(`[plugins.*]`)+ 我们的 materialized 目录还在 → 看起来"装好了",但 trust 没拿到 → hook 永远 fire 不了 → 用户**完全不知情**地用着假装能召回的 setup。

这是 0.8.8 用户主动报的 bug。0.8.9 修复就是引入 trust loop + abort rollback,不再允许 setup 留半截脏数据。

## Force reinstall 跟 trust 的关系

当 hook 内容变了(memorytalk 升级带来新的 `hooks.json`):

1. setup 检测 materialized hash drift → `changed=True`
2. force `uninstall + install`(详见 [hook-installation.md § Force reinstall](hook-installation.md#force-reinstall-on-content-drift))
3. 新 plugin 在 Codex 里是"fresh install",trust hash 失效
4. trust_ok() 返 False → 进 trust loop

也就是说,**每次 hook 内容真变化都会触发一次 re-trust**。这是 Codex 设计决定的代价,**避不掉**。

## trust_ok() 怎么实现

```python
def trust_ok(self) -> bool:
    config_path = Path("~/.codex/config.toml").expanduser()
    if not config_path.exists():
        return False
    text = config_path.read_text()
    return f'[hooks.state."{self._hook_id}"]' in text
```

实现非常简单 —— 看 `[hooks.state]` 下有没有匹配我们 hook id 的 section。Codex 把 trust 信息持久化在那里,有 section 即被 trusted。

我们**不验证 hash 内容**对不对 —— 只看 section 存在性。如果 hash 错(比如用户手动改了),那 hook 自然 fire 不了,probe 会捕获,summary 标 `installed-unverified`。

## 跟 hook-installation.md 的关系

这里只讲 Codex 专属的 trust 部分。整体 step 流程、其他 host 的差别、setup pipeline、adapter 注册表 — 都在 [hook-installation.md](hook-installation.md)。
