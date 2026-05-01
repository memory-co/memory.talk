# Setup Embedding Probe Feedback — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `memory-talk setup` 的 embedding probe 对用户可见 —— 探测期间显示 spinner，成功后输出一行包含 model / dim / 实测延迟的 `✓` 反馈，并把 probe 改成"每次 setup 都跑"（不再受"settings 是否变化"限制）。失败路径不变。

**Architecture:** 三个改动点，按 TDD 拆成 3 个独立 commit：(1) 加纯函数 `_fmt_latency` 并单测；(2) 改 `_step_probe_embedding` 加入计时 + spinner + ✓ 行；(3) 改 `wizard.py` 移除 `embedding_changed` 门禁、把 probe 调用移到"unchanged → return"之前。每个 task 都先写失败测试再做实现。

**Tech Stack:** Python 3.11+ · pytest · click.testing.CliRunner · rich (`Console.status` spinner) · 现有 `validate_embedder` async probe（`memorytalk/provider/embedding.py`）。

**Spec:** `docs/superpowers/specs/2026-05-01-setup-embedding-probe-feedback-design.md`

---

## 涉及文件总览

- **修改**：`memorytalk/cli/setup/steps/embedding.py`
  - 新增私有函数 `_fmt_latency`
  - 重写 `_step_probe_embedding`：spinner + 计时 + 成功行
- **修改**：`memorytalk/cli/setup/wizard.py`
  - 删除 `embedding_changed` 判断
  - 把 `_step_probe_embedding(...)` 调用移到 "config unchanged → return" 之前
- **新增测试文件**：`memorytalk/tests/cli/setup/test_fmt_latency.py`
  - `_fmt_latency` 边界单测
- **修改测试**：`memorytalk/tests/cli/setup/test_first_install_openai/test.py`
  - 断言 stdout 含 `embedding verified` + 模型名 + `dim 1024` + 延迟单位
- **修改测试**：`memorytalk/tests/cli/setup/test_reconfigure_no_change/test.py`
  - 断言 stdout 含 `embedding verified`（证明无字段变化时 probe 仍跑）

不涉及：`validate_embedder` 实现、settings 写盘逻辑、其它 wizard step、PATH takeover、conftest fixtures。

---

## Task 1：添加 `_fmt_latency` 纯函数 + 单测

**Files:**
- Create: `memorytalk/tests/cli/setup/test_fmt_latency.py`
- Modify: `memorytalk/cli/setup/steps/embedding.py`（顶部 import + 新增函数）

**为什么先做这个**：纯函数、零依赖、边界值容易写错（1000ms 究竟归 ms 还是 s？）。单独成 task，这一刻锁死规则，后面 Task 2 直接调用。

- [ ] **Step 1：写失败测试**

新建 `memorytalk/tests/cli/setup/test_fmt_latency.py`：

```python
"""单测：_fmt_latency 在 ms / s 边界的格式。

规则：
- < 1000 ms → "{int}ms"
- ≥ 1000 ms → "{x.x}s"（保留 1 位小数）
"""
from __future__ import annotations

from memorytalk.cli.setup.steps.embedding import _fmt_latency


def test_sub_millisecond_rounds_to_zero_ms():
    assert _fmt_latency(0.0001) == "0ms"


def test_few_hundred_ms():
    assert _fmt_latency(0.412) == "412ms"


def test_just_under_one_second():
    assert _fmt_latency(0.999) == "999ms"


def test_exactly_one_second_uses_seconds():
    assert _fmt_latency(1.0) == "1.0s"


def test_multi_second():
    assert _fmt_latency(12.345) == "12.3s"
```

- [ ] **Step 2：运行测试，确认失败**

```bash
cd /home/twwyzh/mem-go/memory.talk
pytest memorytalk/tests/cli/setup/test_fmt_latency.py -v
```

预期：5 个测试全部 FAIL，错误是 `ImportError: cannot import name '_fmt_latency' from 'memorytalk.cli.setup.steps.embedding'`。

- [ ] **Step 3：实现 `_fmt_latency`**

修改 `memorytalk/cli/setup/steps/embedding.py`。在顶部 imports 区，把现有：

```python
from __future__ import annotations
import asyncio
import sys
```

改成：

```python
from __future__ import annotations
import asyncio
import sys
import time
```

然后在文件靠近顶部、`KNOWN_OPENAI_MODELS` 字典定义**之前**，加入：

```python
def _fmt_latency(seconds: float) -> str:
    ms = seconds * 1000
    if ms < 1000:
        return f"{int(ms)}ms"
    return f"{seconds:.1f}s"
```

注意：`int(ms)` 对 0.0001 秒（即 0.1ms）会得到 `0`，匹配 `test_sub_millisecond_rounds_to_zero_ms`。

- [ ] **Step 4：运行测试，确认通过**

```bash
pytest memorytalk/tests/cli/setup/test_fmt_latency.py -v
```

预期：`5 passed`。

- [ ] **Step 5：跑一下整个 setup 测试套件，确认没引入回归**

```bash
pytest memorytalk/tests/cli/setup/ -v
```

预期：原有所有测试照常通过；新加的 5 个 `test_fmt_latency` 也通过。

- [ ] **Step 6：commit**

```bash
git add memorytalk/cli/setup/steps/embedding.py memorytalk/tests/cli/setup/test_fmt_latency.py
git commit -m "feat(cli/setup): add _fmt_latency helper for probe timing display

Pure function used by the upcoming embedding-probe success line.
Boundary at 1000ms — sub-second values render as '{int}ms', anything
≥1.0s as '{x.x}s'.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2：embedding probe 加 spinner + 成功反馈行

**Files:**
- Modify: `memorytalk/cli/setup/steps/embedding.py:172-184`（`_step_probe_embedding` 函数体）
- Modify: `memorytalk/tests/cli/setup/test_first_install_openai/test.py`（追加断言）

**做什么**：在 `_step_probe_embedding` 成功路径上加 `err_console.status(...)` spinner、`time.perf_counter()` 计时、以及 `✓ embedding verified · {model} · dim {dim} · {latency}` 的输出行。失败分支保持原样。

- [ ] **Step 1：先写失败测试 —— 在已有的 first-install OpenAI 测试里追加断言**

修改 `memorytalk/tests/cli/setup/test_first_install_openai/test.py`，在文件最末尾、`assert "text-embedding-v4" in result.stdout` 这一行**之后**追加：

```python
    # Probe 成功反馈行：含 "embedding verified" + 模型名 + dim + 延迟单位
    assert "embedding verified" in result.stdout
    assert "dim 1024" in result.stdout
    # mock 的 httpx probe 同步返回 → 延迟必然 < 1s，单位一定是 "ms"
    assert "ms" in result.stdout
```

注意：`"text-embedding-v4" in result.stdout` 这条断言在原文件里已经存在，新增的三条放在它后面即可，不要重复加 model name 断言。

- [ ] **Step 2：运行测试，确认失败**

```bash
pytest memorytalk/tests/cli/setup/test_first_install_openai/ -v
```

预期：`AssertionError: assert 'embedding verified' in result.stdout`（因为当前 `_step_probe_embedding` 成功时静默 return）。

- [ ] **Step 3：重写 `_step_probe_embedding`**

修改 `memorytalk/cli/setup/steps/embedding.py`。把整个 `_step_probe_embedding` 函数（当前在第 172-184 行附近）替换为：

```python
def _step_probe_embedding(cfg: Config, new_settings: dict) -> None:
    cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]
    while True:
        try:
            t0 = time.perf_counter()
            with err_console.status("[dim]validating embedding endpoint…[/dim]"):
                asyncio.run(validate_embedder(cfg))
            elapsed = time.perf_counter() - t0
            emb = new_settings["embedding"]
            err_console.print(
                f"[green]✓[/green] embedding verified · "
                f"{emb['model']} · dim {emb['dim']} · {_fmt_latency(elapsed)}"
            )
            return
        except EmbedderValidationError as e:
            err_console.print(f"[red]embedding probe failed:[/red] {e}")
            if not _prompt.confirm("Re-edit embedding fields?", default=True):
                sys.exit(1)
            new_settings.update(_step_embedding(new_settings))
            cfg._settings = Settings(**new_settings)  # type: ignore[attr-defined]
```

要点：
- `err_console.status(...)` 是 rich 的 spinner 上下文管理器；在非 TTY（CliRunner）下它会降级为静默或一次性打印，不会破坏断言。
- 计时用 `time.perf_counter()`（高分辨率单调时钟），包住整个 `asyncio.run(validate_embedder(cfg))`，所测的就是用户感知的等待时间。
- `model` / `dim` 从 `new_settings["embedding"]` 取，不依赖 `validate_embedder` 返回值 —— 探针的"raise on failure / return None on success"契约保持不变。
- 失败分支与原来**完全一致**（`err_console.print(...)` + `confirm` + `sys.exit(1)` + 重收集字段）。

- [ ] **Step 4：运行 first-install 测试，确认通过**

```bash
pytest memorytalk/tests/cli/setup/test_first_install_openai/ -v
```

预期：`1 passed`。

- [ ] **Step 5：跑全部 setup 测试，确认没破坏其它场景**

```bash
pytest memorytalk/tests/cli/setup/ -v
```

预期：所有测试通过。`test_reconfigure_changed`（probe 也会被调到）、`test_first_install_local`、`test_optout_uses_current_env` 都已 mock probe，新增的 ✓ 输出不影响它们的断言。`test_reconfigure_no_change` 这一刻仍然不会跑 probe（gate 还在），所以也不受影响。

- [ ] **Step 6：commit**

```bash
git add memorytalk/cli/setup/steps/embedding.py memorytalk/tests/cli/setup/test_first_install_openai/test.py
git commit -m "feat(cli/setup): show ✓ embedding verified line after probe

Wraps the probe in a rich status spinner during the call and prints a
single confirmation line on success with model, configured dim, and
observed latency. Failure path unchanged (re-edit loop on
EmbedderValidationError).

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3：probe 改成"每次 setup 都跑"

**Files:**
- Modify: `memorytalk/cli/setup/wizard.py:73-89`（diff 判定 + probe 调度块）
- Modify: `memorytalk/tests/cli/setup/test_reconfigure_no_change/test.py`（追加断言）

**做什么**：删 `embedding_changed` 门禁，把 `_step_probe_embedding(cfg, new_settings)` 调用提到 "config unchanged → return" 这条早返回**之前**。这样无论 settings 变没变，每次 `memory-talk setup` 都会触发一次真实 probe 作为健康检查。

- [ ] **Step 1：先写失败测试 —— 让 no-change 场景断言 probe 跑过了**

修改 `memorytalk/tests/cli/setup/test_reconfigure_no_change/test.py`，在最末尾、`assert "nothing" in result.stdout.lower() and "unchanged" in result.stdout.lower()` 这一行**之后**追加：

```python
    # 即便 settings 没变，probe 也应跑过（健康检查语义）
    assert "embedding verified" in result.stdout
```

- [ ] **Step 2：运行测试，确认失败**

```bash
pytest memorytalk/tests/cli/setup/test_reconfigure_no_change/ -v
```

预期：`AssertionError: assert 'embedding verified' in result.stdout`（因为当前 wizard 在 no-change 分支会提前 return，根本没进 probe）。

- [ ] **Step 3：改 `wizard.py`**

打开 `memorytalk/cli/setup/wizard.py`。当前第 73-89 行附近的代码块是：

```python
    # 4. diff
    changed = diff_settings(old_raw or {}, new_settings) if old_raw else ["(initial)"]

    if old_raw is not None and not changed:
        err_console.print("\n[dim]config unchanged — nothing to write[/dim]")
        return {
            "settings_changed": [],
            "wrote_settings": False,
            "ensured_dirs": False,
            "server": None,
            "first_install": False,
        }

    # 5. embedding probe (only if embedding section actually differs OR first install)
    embedding_changed = old_raw is None or new_settings.get("embedding") != (old_raw.get("embedding") or {})
    if embedding_changed:
        _step_probe_embedding(cfg, new_settings)
```

替换为：

```python
    # 4. diff
    changed = diff_settings(old_raw or {}, new_settings) if old_raw else ["(initial)"]

    # 5. embedding probe — always run, even on no-op reconfigure, so the
    #    user gets a positive health-check signal each time `setup` is run.
    _step_probe_embedding(cfg, new_settings)

    if old_raw is not None and not changed:
        err_console.print("\n[dim]config unchanged — nothing to write[/dim]")
        return {
            "settings_changed": [],
            "wrote_settings": False,
            "ensured_dirs": False,
            "server": None,
            "first_install": False,
        }
```

要点：
- 删除 `embedding_changed = ...` 这一行和它下面的 `if embedding_changed:` 守卫。
- probe 的调用挪到 `if old_raw is not None and not changed:` **之前**。
- "config unchanged → nothing to write" 这条早返回保留 —— 它只决定要不要写盘 / 重启 server，不影响 probe 是否跑。
- 写盘后续路径（`write_settings_atomic` / `ensure_dirs` / `_step_server`）逻辑不动。

边界说明（不需要写代码，仅供你审 diff 时确认）：probe 失败时会进入 `_step_probe_embedding` 内部的 re-edit 循环，用户改了字段后，原来 no-change 的 diff 自然变成 has-change，wizard 会顺势走入写盘分支 —— 这是想要的行为。

- [ ] **Step 4：运行 no-change 测试，确认通过**

```bash
pytest memorytalk/tests/cli/setup/test_reconfigure_no_change/ -v
```

预期：`1 passed`。`"nothing" + "unchanged"` 断言依旧成立（早返回行还在），新增的 `"embedding verified"` 也成立。

- [ ] **Step 5：跑完整 setup 测试套件**

```bash
pytest memorytalk/tests/cli/setup/ -v
```

预期：所有用例通过。需要特别留意的是：
- `test_first_install_openai` / `test_first_install_local` / `test_reconfigure_changed`：probe 一直就会跑，行为不变。
- `test_reconfigure_no_change`：probe 现在也跑，已 mock，✓ 行出现。
- `test_optout_uses_current_env`：probe 用 `local` 分支并已 monkey-patch 成 noop。
- `test_path_takeover`、`test_bootstrap_real_venv`：与 embedding 流程无关。

- [ ] **Step 6：commit**

```bash
git add memorytalk/cli/setup/wizard.py memorytalk/tests/cli/setup/test_reconfigure_no_change/test.py
git commit -m "feat(cli/setup): probe embedding on every setup, not just on change

Removes the embedding_changed gate and moves the probe call ahead of the
'config unchanged → nothing to write' early-return. Re-running setup
without editing anything is now a meaningful health check, and the user
always sees a ✓ embedding verified line.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 验收

三个 commit 全部落盘后，做一次端到端手动验证：

```bash
pytest memorytalk/tests/cli/setup/ -v
```

预期：全部测试通过（包括三个新增 / 修改的断言）。

如果机器上有真实可用的 `QWEN_KEY` 环境变量，可以可选地手跑一次 `memory-talk setup` 看实际终端效果（spinner 转一下 → 立刻被 `✓ embedding verified · text-embedding-v4 · dim 1024 · ###ms` 替换）。这一步不在测试套件覆盖内，仅用于视觉确认。

## 不在范围内（明确排除）

- 其它 wizard step（vector / relation / server port / PATH takeover）的同款反馈 —— 留给后续 spec。
- 修改 `validate_embedder` 的返回类型或契约。
- 任何"上次刚 probe 过，跳过"的缓存机制 —— spec 明确要求每次都验。
- 调整 server step / 写盘 / ensure_dirs 顺序。
