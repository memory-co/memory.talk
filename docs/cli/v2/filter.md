# filter

**取景框（viewfinder）**：用脚本表达"哪些 session / card 值得被二次加工或反思"，并提供一致的 list / run / undo 入口。

每个 filter 是一个语义化的"待处理视野"。它的存在本身比一次跑出多少结果更重要 —— 因为数据是流动的：sync 进新 session、新 card 创建、tag 状态变化，**今天框里没东西，过几天就有了**。filter 是 memory.talk 里"我应该回头看哪些"的对象化表达。

跟 search 容易混，但语义不同：

| | `search` | `filter` |
|---|---|---|
| 触发动机 | "我现在想找 X" | "哪些还没被我 X" |
| 意识形态 | **有意识**地查 | 框定**应当被反思**的视野 |
| 生命周期 | 一次性 | 长期存在，反复跑 |
| 形态 | 一次 query | 一段脚本 + 配套撤标 |

典型 filter：

- 哪些 session 还没抽过 base card
- 哪些 card 还没经过周末复盘
- 哪些 session 没生成英文摘要
- 哪些 card 的 TTL 快到、值得回顾续命

memory.talk 不内置任何 filter；它只负责"发现、跑、配套撤标"。filter 框什么、做什么，由用户的脚本定义。filter 跟 [tag](tag.md) 是天然搭配 —— tag 做"已处理"标记，filter 用 `NOT (tag = "X")` 自然就只看到未处理的。

## 目录布局

filter 目录在 **memory-talk 的 data_root 下**（默认 `~/.memory-talk/`，被 `MEMORY_TALK_DATA_ROOT` 环境变量覆盖）：

```
<data_root>/filters/
├── new-session/
│   ├── filter.py
│   └── unfilter.py        (可选)
├── stale-cards/
│   └── filter.py
└── ...
```

约定：

| 文件 | 必填 | 作用 |
|---|---|---|
| `<dir>/filter.py` | ✅ | 框出待处理对象 → 处理 → 打标"已处理" |
| `<dir>/unfilter.py` | 可选 | 撤标，让取景框重新看到这些对象 |
| `<dir>/*` | — | 任意辅助（helper、config.json、prompt 模板等） |

**filter 名字 = 子目录名**，必须匹配正则 `^[a-z][a-z0-9_-]*$`（小写字母开头，后续字符可为小写字母 / 数字 / `_` / `-`）。不匹配的目录在 list 时被静默忽略，run / undo 时报错 `invalid filter name`。这条白名单防：

- 路径注入（`..` / 绝对路径片段）
- 大小写敏感跨平台问题
- 跟 shell 元字符 / glob 字符冲突

memory.talk **不**自动 scaffold filter 目录。后续 `setup` wizard 会加一个可选步骤"装一份示例 filter"；本期版本里用户自己 mkdir + 写文件即可。

## 子命令

### filter list

```bash
memory-talk filter list [--json]
```

枚举 `<data_root>/filters/` 下所有合法 filter 子目录。"合法"的判定：

- 目录名匹配 `^[a-z][a-z0-9_-]*$` 白名单
- 内含 `filter.py`

**列表里"当前没数据可处理"的 filter 也会出现** —— filter 是一个**取景框**，框里此刻空不代表它没用。是否值得跑由用户决定，list 只回答"装了哪些、可以跑哪些"。

**Markdown（默认）：**

```markdown
# filters (3)

| name | undo |
|---|---|
| new-session | yes |
| stale-cards | — |
| weekly-digest | yes |
```

**JSON（`--json`）：**

```json
{
  "filters": [
    {"name": "new-session", "has_undo": true},
    {"name": "stale-cards", "has_undo": false},
    {"name": "weekly-digest", "has_undo": true}
  ]
}
```

### filter run

```bash
memory-talk filter run <name> [-- <args>...]
```

跑指定 filter 的 `filter.py`：

- 用 **`sys.executable`** 启动子进程（确保跟 memory-talk 同一个 venv —— 脚本里 `import` 的依赖跟 memory-talk 一致）
- 工作目录 = `<data_root>/filters/<name>/`（脚本可以放相对路径的辅助文件）
- stdout / stderr **直接透传**到当前终端（不缓冲、不包装）
- exit code 透传（脚本失败 = `filter run` 失败）
- `--` 后面的参数原样传给 filter.py 的 `sys.argv[1:]`

例：

```bash
# 跑取景框现在框出来的所有候选
memory-talk filter run new-session

# 透传额外参数（filter.py 自己解析）
memory-talk filter run new-session -- --limit 5 --dry-run
```

### filter undo

```bash
memory-talk filter undo <name>
```

跑 `unfilter.py`，参数 / 工作目录约定同 run。

`unfilter.py` 不存在时报错 `no undo defined for filter <name>`，exit 1。

> 撤标的语义是"把取景框重置到能再次看到这些对象"，**不是**回滚已发生的副作用（删掉抽出来的 card、回退 link 等）。如果用户想完全回到 filter 跑之前的状态，自己在 `unfilter.py` 里实现。memory.talk 不假设你想要哪种粒度的回滚。

## filter.py 怎么写

filter.py 是普通 Python 脚本，**memory.talk 不强加 API 契约**。但典型骨架：

```python
#!/usr/bin/env python3
"""<filter_name>: <一句话描述这个取景框框的是什么>"""
import json
import subprocess
import sys


def mt(*args, capture: bool = True) -> dict | None:
    """跑 memory-talk 子命令，capture=True 时解析 JSON 返回。"""
    cmd = ["memory-talk", *args]
    if capture and "--json" not in args:
        cmd.append("--json")
    proc = subprocess.run(cmd, capture_output=capture, text=True, check=True)
    return json.loads(proc.stdout) if capture else None


def main() -> int:
    # 1. 把"待处理"的视野框出来（tag 反向过滤是最常用的写法）
    resp = mt("search", "", "--where", 'NOT (tag = "base-card")')
    sessions = resp["sessions"]["results"]
    if not sessions:
        print("nothing in frame today")
        return 0

    print(f"in frame: {len(sessions)} session(s)")
    for s in sessions:
        sid = s["session_id"]
        try:
            do_work(sid)             # 业务逻辑：抽 card / 反思 / 总结 / ...
            mt("tag", "add", sid, "base-card", capture=False)
        except Exception as e:
            print(f"  ✗ {sid}: {e}", file=sys.stderr)
            # 出错不打标 → 下次还会被框进来，自然重试

    return 0


def do_work(session_id: str) -> None:
    """业务逻辑：抽 card、加 link、调 LLM 反思、写文件等。"""
    raise NotImplementedError("fill in your filter logic")


if __name__ == "__main__":
    sys.exit(main())
```

约定（建议遵守，不强制）：

1. **filter.py 通过 `memory-talk` CLI 跟服务通信**（不要 `import memorytalk` 绕进去 —— 那条路径绕开了 server，state 会乱）
2. **打标用 tag**：`tag add <id> <key>` 标"已处理"，下次 filter run 自然过滤掉
3. **失败不打标**：处理出错不打标，让下次重跑能自动捡起来 —— 取景框的"断点续跑"靠这个
4. **打印进度**：filter 跑长任务时把进度 print 出来；stdout 是用户能看到的唯一反馈

## 完整示例：`new-session`

**取景框含义**：所有还没抽过 base card 的 session（即没有 `base-card` tag 的）。

**处理动作**：对每个 session 抽一张总结 card，并打 `base-card` tag。

### `<data_root>/filters/new-session/filter.py`

```python
#!/usr/bin/env python3
"""new-session: 框出还没抽 base card 的 session，给每个抽一张总结 card。"""
import json
import subprocess
import sys


def mt(*args, capture=True):
    cmd = ["memory-talk", *args]
    if capture and "--json" not in args:
        cmd.append("--json")
    proc = subprocess.run(cmd, capture_output=capture, text=True, check=True)
    return json.loads(proc.stdout) if capture else None


def main() -> int:
    resp = mt("search", "", "--where", 'NOT (tag = "base-card")')
    sessions = resp["sessions"]["results"]
    if not sessions:
        print("no new sessions in frame")
        return 0

    print(f"in frame: {len(sessions)} session(s)")
    for s in sessions:
        sid = s["session_id"]
        print(f"→ {sid}")
        # 替换成真实的总结逻辑（调 Claude / OpenAI 反思抽 card）。
        # 演示：直接拿 session 头几轮做一张占位 card。
        round_count = s.get("round_count", 0) or 5
        last_idx = min(round_count, 5)
        rounds_arg = json.dumps([{"session_id": sid, "indexes": f"1-{last_idx}"}])
        mt(
            "card", "create", "--summary", f"base card for {sid}",
            "--rounds", rounds_arg,
            capture=False,
        )
        mt("tag", "add", sid, "base-card", capture=False)
        print(f"  ✓ tagged base-card")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### `<data_root>/filters/new-session/unfilter.py`

```python
#!/usr/bin/env python3
"""new-session undo: 撤所有 session 的 base-card tag，让取景框重新看到它们。"""
import json
import subprocess
import sys


def main() -> int:
    proc = subprocess.run(
        ["memory-talk", "search", "", "--where", 'tag = "base-card"', "--json"],
        capture_output=True, text=True, check=True,
    )
    sessions = json.loads(proc.stdout)["sessions"]["results"]
    if not sessions:
        print("nothing in frame to un-tag")
        return 0

    for s in sessions:
        subprocess.run(
            ["memory-talk", "tag", "remove", s["session_id"], "base-card"],
            check=True,
        )
    print(f"unmarked {len(sessions)} session(s) — they're back in frame")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### 用法

```bash
# 第一次跑：把当下所有 session 都抽一遍
memory-talk filter run new-session

# 后续 sync 进新 session 后，再跑 —— 取景框只框出新增的
memory-talk filter run new-session

# 强制全量重跑（先撤标，再跑）
memory-talk filter undo new-session
memory-talk filter run new-session
```

## 错误

| 情况 | Markdown（stderr） | exit |
|---|---|---|
| `<data_root>/filters/` 不存在 | list 时显示空列表 + 一行提示；run 时报 `**error:** filters dir not found at <path>` | list=0 / run=1 |
| `filter run <name>` 但目录不存在 | `**error:** filter not found: <name>` | 1 |
| 目录存在但缺 `filter.py` | `**error:** filter <name> has no filter.py` | 1 |
| `<name>` 不匹配白名单 | `**error:** invalid filter name: <name>` | 1 |
| `filter undo <name>` 但缺 `unfilter.py` | `**error:** no undo defined for filter <name>` | 1 |
| filter.py / unfilter.py 自己 exit 非零 | 透传子进程的 stderr | 子进程的 exit code |

## 设计取舍

### 为什么把 filter 定位成"取景框"而不是"批处理任务"？

差别在心智模型：

- **批处理任务**：一次性的、有明确开始结束，"跑完就归档"
- **取景框**：长期存在的、对动态数据流的持续关注 —— "这事儿值得我反复回头看"

memory.talk 里的 session / card 是流式增长的（sync 持续进数据、新 card 持续抽出来）。任何"对一类对象的反思"都是一个**长期议题**，今天处理完了不代表事儿结了，明天又有新数据进来。把 filter 命名为"取景框"是给用户一个**对象化、可命名、能 list 出来**的概念，让"我应该回头看哪些视角"这件事在工具里有显式表达。

副产品：当用户的 `filter list` 越来越长时，本身就是工作流复杂度的可视化 —— 哪些反思视角已经被对象化了一目了然。

### 为什么是 subprocess + 用户脚本，不是 plugin / hook system？

memory.talk 的核心契约是"管理 session / card / link / tag 的存储 + 检索"。**取景框对应的处理动作**形态各异：调不同的 LLM、写不同的 card 模板、对接不同的下游。

把动作放进 memory.talk 主仓有两个糟糕选择：

1. **写死一种动作**：只解决一类问题，其它用户不会用
2. **做 plugin 系统**：要定义稳定的 Python API、考虑版本兼容、做 sandbox —— 复杂度爆炸，收益小

filter 选了"用户自己写脚本，我们只负责发现 + 跑"这种最薄的层。用户脚本通过 CLI 跟 memory.talk 通信，这条边界清晰、稳定、易调试（脚本里每个命令都能在终端独立复现）。

### 为什么不让 filter.py 直接 import memorytalk？

绕开 HTTP server 直接动 db / vectors 会**漏掉服务层的写入流**（events、TTL 续命、indexing 副作用）。filter 跑完看着 db 对了但 vector index 没更新这种 bug 极难排查。**强约定走 CLI / HTTP**，状态机一致。

### 为什么 filter 名字是目录而不是单文件？

留扩展空间：

- `unfilter.py` 配套
- `helper.py`、`config.json`、`prompt-template.md` 等辅助
- 未来可能的 `meta.json`（取景框描述、推荐运行周期等）

单文件 filter 形态局限太多。

### 跟 cron / 定时器的关系

filter 是**幂等的取景框逻辑**，不是调度器。跟 cron / launchd / systemd timer 配合即可定时刷新：

```cron
0 */6 * * *  /usr/local/bin/memory-talk filter run new-session
```

memory.talk 自己**不**管定时调度。
