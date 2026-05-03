# filter

**取景框（viewfinder）**：一个带名字的查询 + 一组声明式的 tag 操作。

filter **不**做任何分析、提炼、生成工作。它只做两件事：

1. **看**：filter.py 输出"当下框里有哪些 subject"
2. **改 tag 状态**：`filter mark <name> <id>` 给指定 subject 应用预声明的 tag ops；`filter unmark` 反向

抽 card、反思、写报告、调 LLM —— 这些**在 memory-talk 之外**进行，filter 不参与。`filter mark` 只是"用户告诉系统：这一条我处理完了，按 meta 给它打标"。

## 用 filter 解决什么问题

memory-talk 里的 session / card 是流动的，"哪些值得回头看"这件事天然适合用一个**对象化的、可命名的、状态可逆的视野**来管理。每个 filter 就是这样一个视野。

跟 [search](search.md) 容易混：

| | `search` | `filter` |
|---|---|---|
| 做什么 | 一次查询 | **命名**的查询 + tag op schema |
| 生命周期 | 一次性 | 长期存在，反复跑 |
| 工作动作 | 不做 | **不做** |
| 形态 | 一条命令 | 一段脚本 + 一份 meta |

filter 跟 [tag](tag.md) 是天然搭配 —— tag 提供持久状态，filter 提供"基于 tag 状态的命名视野 + 状态切换"。

## 目录布局

filter 目录在 **memory-talk 的 data_root 下**（默认 `~/.memory-talk/`，被 `MEMORY_TALK_DATA_ROOT` 环境变量覆盖）：

```
<data_root>/filters/
├── new-session/
│   ├── filter.py
│   └── meta.json
├── stale-cards/
│   ├── filter.py
│   └── meta.json
└── ...
```

约定：

| 文件 | 必填 | 作用 |
|---|---|---|
| `<dir>/filter.py` | ✅ | **纯 selector**：输出当下框里的 subject_ids |
| `<dir>/meta.json` | ✅ | 声明 `mark_tag` 的 `add` / `remove` 列表 |
| `<dir>/*` | — | 任意辅助（helper、prompt 模板等，filter 自己用）|

**filter 名字 = 子目录名**，必须匹配正则 `^[a-z][a-z0-9_-]*$`。不匹配的目录在 list 时静默忽略，run/mark/unmark 时报错 `invalid filter name`。

memory.talk **不**自动 scaffold filter 目录。后续 `setup` wizard 会加可选步骤"装一份示例 filter"；本期版本里用户自己 mkdir + 写文件即可。

## meta.json 契约

```json
{
  "mark_tag": {
    "add": ["_filter:new-session"],
    "remove": []
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `mark_tag.add` | string[] | 任一非空 | `mark <id>` 时给该 subject 加的 tag 列表 |
| `mark_tag.remove` | string[] | 任一非空 | `mark <id>` 时给该 subject 撤的 tag 列表 |

`add` / `remove` 都可空但**不能同时为空**（那种 filter 没意义）。两侧都列时，`mark` 对每个 subject 先 add 再 remove。

`unmark` 字面反向 —— `add` 列表里的 tag 撤掉、`remove` 列表里的 tag 加回。详情见下面 `filter unmark` 一节。

**tag 命名建议**：内部 marker tag 用 `_filter:<name>` 前缀（下划线开头）。view / log / tag list 默认隐藏 `_` 开头的 tag，避免污染用户视野。普通 tag（`base-card` / `reviewed` / `topic:lancedb`）是用户语义的，filter 用就让它们正常显示。

## filter.py 契约

filter.py 是一个 **Python 模块**，必须导出一个函数：

```python
def select(client) -> list[str]:
    """返回当前框里的 subject_ids。"""
```

`client` 是框架注入的可调用对象，签名跟 memory-talk HTTP API 一一对应：

```python
client(method: str, path: str, *,
       json_body: dict | None = None,
       params: list[tuple[str, str]] | dict | None = None) -> dict
```

它在内部直接调用 CLI 用的同一个 `_http.api()`，**不是 subprocess**。这意味着：

- 框架 + filter.py 共享同一个 Python 进程（filter.py 不会 fork、不会再启动 server）
- 测试里框架的 ASGI 注入（test client）对 filter.py 透明生效，filter 测试路径跟 CLI 完全一致
- filter 作者只写 `client(...)` 调用，不需要管 HTTP / subprocess / `import memorytalk` 这些底层

完整示例（new-session 内置 filter）：

```python
"""new-session: 框出还没打 _filter-new-session 标的 session。"""
from typing import Callable


def select(client: Callable) -> list[str]:
    resp = client("POST", "/v2/search", json_body={
        "query": "",
        "where": 'tag != "_filter-new-session"',
    })
    return [s["session_id"] for s in resp["sessions"]["results"]]
```

约定：

- `select` **必须存在**，缺失 → run 报错
- 返回值必须是 `list[str]`，每个元素为 subject_id（`sess_*` 或 `card_*`）
- 元素被 strip；空字符串忽略
- 抛异常 → run 失败，异常类型和 message 透传到 stderr

filter.py 可以用 stdlib（json / 数据处理）以及任意已安装的依赖；但**不要直接 import memory-talk 服务层** —— 用 `client` 走 HTTP API，状态机一致。

## 子命令

### filter list

```bash
memory-talk filter list [--json]
```

枚举 `<data_root>/filters/` 下所有合法 filter（含 `filter.py` + `meta.json`，且目录名通过白名单）。

**列表里"当下框里没东西"的 filter 也会出现** —— filter 是个长期存在的视野，今天框里 0 条不代表它没用。

**Markdown：**

```markdown
# filters (3)

| name | mark_tag |
|---|---|
| new-session | +`_filter:new-session` |
| stale-cards | -`stale` |
| weekly-review | +`reviewed` -`needs-review` |
```

### filter run

```bash
memory-talk filter run <name> [--json]
```

跑 filter.py，输出当下框里的 subject_ids。**只是看，不改任何状态**。

**Markdown：**

```markdown
# filter run `new-session` (3)

- `sess_aa`
- `sess_bb`
- `sess_cc`
```

**JSON：**

```json
{
  "filter": "new-session",
  "subject_ids": ["sess_aa", "sess_bb", "sess_cc"]
}
```

`run` 是 read-only。你看到这些 id，**自己**在 memory-talk 之外对它们做实际工作（抽 card、调 LLM、写报告、whatever），然后用 `mark` 一个个标记完成。

### filter mark

```bash
memory-talk filter mark <name> <subject_id>... [--json]
```

对指定的一个或多个 subject **应用 meta.json 里的 mark_tag ops**：先 add 列表里的所有 tag，再 remove 列表里的所有 tag。

`mark` **不**调 filter.py。它就是个声明式的批量 tag 操作，参数里给的 subject_id 才是真理来源。

```bash
# 单条
memory-talk filter mark new-session sess_aa

# 批量
memory-talk filter mark new-session sess_aa sess_bb sess_cc
```

**Markdown：**

```markdown
# filter mark `new-session` (3)

- `sess_aa`: +`_filter:new-session`
- `sess_bb`: +`_filter:new-session`
- `sess_cc`: +`_filter:new-session`
```

**JSON：**

```json
{
  "filter": "new-session",
  "applied": [
    {"subject_id": "sess_aa", "added": ["_filter:new-session"], "removed": []},
    {"subject_id": "sess_bb", "added": ["_filter:new-session"], "removed": []},
    {"subject_id": "sess_cc", "added": ["_filter:new-session"], "removed": []}
  ]
}
```

不验证 subject 是否存在 —— 直接调 `tag add/remove`，不存在会从 API 层报 404。`mark` 单条报错继续处理下一条，最终 exit 0；如果所有条都失败，exit 1。

### filter unmark

```bash
memory-talk filter unmark <name> [<subject_id>...] [--json]
```

**反向** meta.json 的 mark_tag ops：把 `add` 列表里的 tag 撤掉、把 `remove` 列表里的 tag 加回。

- 不传 subject_id → 反向应用到**所有相关 subject**：
  - `add` 列表里每个 tag → 找出所有打了它的 subject，撤掉
  - `remove` 列表里每个 tag → 找出所有没打它的 subject，加上
- 传 subject_id → 仅对这些 subject 反向应用

注意 `mark_tag.remove` 列表的全量 unmark 会"过打"（给从未涉及的 subject 也打 tag）。这是 OK 的 —— filter 的 scan 条件决定谁该出现在框里，跑一遍 `filter run` 就知道。filter 不保证 unmark 是精确历史回滚。

```bash
# 撤一条
memory-talk filter unmark new-session sess_aa

# 全量重置
memory-talk filter unmark new-session
```

输出格式跟 `mark` 镜像（每行的 ops 反向）。

## 完整示例：`new-session`

**取景框含义**：所有还没打 `_filter:new-session` tag 的 session。

**用法**：周期性扫一遍最近的 session 抽 base card —— 抽 card 这事儿你**自己**做（人工 / LLM / 别的脚本，反正不归 memory-talk 管）。filter 只负责：
1. 给你看哪些没处理过（`run`）
2. 你处理完一条之后帮你标记一下（`mark <id>`）
3. 想重做就反标（`unmark`）

### `<data_root>/filters/new-session/filter.py`

```python
"""new-session: 框出还没打 _filter-new-session 标的 session。"""
from typing import Callable


def select(client: Callable) -> list[str]:
    resp = client("POST", "/v2/search", json_body={
        "query": "",
        "where": 'tag != "_filter-new-session"',
    })
    return [s["session_id"] for s in resp["sessions"]["results"]]
```

### `<data_root>/filters/new-session/meta.json`

```json
{
  "mark_tag": {
    "add": ["_filter:new-session"]
  }
}
```

### 实际工作流

```bash
# 1. 看下当下框里有谁
$ memory-talk filter run new-session
# filter run `new-session` (3)
# - sess_aa
# - sess_bb
# - sess_cc

# 2. 你自己对 sess_aa 做实际工作（抽 card / 调 LLM / 写报告 / ...）
#    memory-talk 不参与。

# 3. 处理完 sess_aa 了，标记一下
$ memory-talk filter mark new-session sess_aa
# filter mark `new-session` (1)
# - sess_aa: +_filter:new-session

# 4. 接着处理 sess_bb、sess_cc，逐条 mark
$ memory-talk filter mark new-session sess_bb
$ memory-talk filter mark new-session sess_cc

# 5. 也可以批量 mark（如果你一次性都处理完了）
$ memory-talk filter mark new-session sess_aa sess_bb sess_cc

# 6. 下次 sync 进 5 条新 session，再 run 一次
$ memory-talk filter run new-session
# filter run `new-session` (5)
# - sess_dd
# ...

# 7. 想从头再来？unmark 全部
$ memory-talk filter unmark new-session
```

## 错误

| 情况 | exit |
|---|---|
| `<data_root>/filters/` 不存在 | list=0（空列表）/ run/mark/unmark=1 |
| `filter <name>` 但目录不存在 | 1 |
| 目录缺 `filter.py` 或 `meta.json` | 1 |
| 名字不匹配白名单 | 1 |
| meta.json 解析失败 / `mark_tag` 字段缺失 | 1 |
| `mark_tag.add` 和 `mark_tag.remove` 都为空 | 1 |
| filter.py 自己 exit 非零 | 透传 |
| `mark` / `unmark` 里某条 subject_id 不存在 | 单条报错继续，全部失败才 exit 1 |

## 设计取舍

### filter 不做工作 —— 取景框就是看的

filter 的职责严格限定在"看 + 改 tag 状态"。任何"分析 / 提炼 / 生成"动作（抽 card、调 LLM、写报告等）都在 memory-talk **外部**进行，由用户用任何工具完成。

这条边界让 filter 的 contract 简单到极致：用户写一段 query 脚本 + 一行 meta，就拥有一个**命名的、可重置的、状态化的**视野。所有的复杂性留给"做工作"那一步，那一步本来就形态各异，不该塞进 memory-talk。

### 为什么 `mark` 是 per-subject 而不是"mark all"

实际工作流是**逐条处理**的：用户对 `sess_aa` 抽完 card 后，立刻要标记完成；不会傻等全部 N 条都处理完才统一打标。中途如果出错或者中断，已经处理的那几条也不应丢失打标。

per-subject 的 `mark` 直接对应这个工作流：处理完一条 `mark` 一条，自然支持断点续做。要批量也行（命令行支持多 subject_id 参数）。

### 为什么 `mark` 不调 filter.py 验证

`mark <id>` 的语义是"我刚处理完这一条，给我标记"。这一刻 subject 是不是还在 filter.py 的视野里**无关紧要** —— 用户处理时它在视野里就够了。强行验证反而把"做事"和"标记"绑进同一个事务，复杂化。

### 为什么 mark / unmark 是框架内置而不是用户脚本

mark_tag ops 是**纯声明性**的（一组 add、一组 remove），不需要用户编程。声明式 meta.json + 框架内置实现把这部分共性抽出来；用户只需要写真正不同的部分（filter.py 的查询逻辑）。

### 为什么 filter.py 是 Python 模块（in-process）而不是 subprocess

最初版本设计为 subprocess（`sys.executable filter.py`，stdout 一行一个 id）。这种契约的好处是 filter.py 可以是任何可执行文件 —— shell / awk / Python 都行。但有两个真实代价：

1. **测试路径不一致**：CLI 主体走 ASGI test client，但 subprocess 起的 filter.py 看不到这条 in-process 路径，要嘛硬启 HTTP server，要嘛在测试里硬塞合成 filter 绕开 —— 测试覆盖跟生产语义差一截。
2. **重复造轮子**：每个 filter.py 都得自己 import json / subprocess / 拼命令行，等于把 memory-talk CLI 的封装在 filter 这一层重新做一遍。

切换到 module + `select(client)` 契约之后：
- 测试和生产**完全同路径**（都走 `_http.api()`）
- filter 作者只写一个 Python 函数
- 失去"任意可执行文件"的灵活性 —— 但 filter 写 Python 是合理默认（memory-talk 已经是 Python 工具链）

如果未来真有"非 Python 脚本"需求（罕见），加一个 fallback 探测就够了，不影响主路径。

### 跟 cron / 定时器的关系

filter 是**幂等的视野 + tag op**，不是调度器。如果某个 filter 的 mark 流程能完全自动化（比如脚本化的 LLM 总结），可以拿 cron 包：

```cron
# 每 6 小时跑一次：扫候选 → 调脚本处理 → 逐条 mark
0 */6 * * *  /home/me/scripts/process-new-sessions.sh
```

`process-new-sessions.sh` 自己拼 `filter run` + 实际工作 + `filter mark`。memory.talk 自己**不**管定时调度。
