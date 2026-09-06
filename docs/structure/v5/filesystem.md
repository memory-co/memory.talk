# Filesystem (v5)

`~/.memory.talk/` 下只有两样:一个 git 仓库,一堆裸文件。**没有数据库,没有索引**;每个字节都是 canonical。为什么见 [`../../works/v5/store.md`](../../works/v5/store.md)。

```
~/.memory.talk/                     ← MEMORY_TALK_HOME
├── memory/                         ← git 仓库(认知层)
│   ├── .git/
│   ├── README.md                   ← init 时写的一句说明
│   ├── cards/
│   │   └── <dir>/…/<slug>.md       ← 一张卡一个 markdown(frontmatter + 正文);目录即分类
│   └── issues/
│       └── <issue_id>.json         ← 一个 issue 一个 JSON(问题 / 立场 / 论证 / 边)
└── tasks/                          ← 裸文件(现场层)
    └── <task_id>/
        ├── task.json               ← 目标 / 项目 / 父 / 状态
        ├── canvas.json             ← 画布(视图);不存在 = 空画布
        ├── sessions.json           ← 会话登记(数组,现场)
        ├── members.json            ← 成员(人):谁在操作 / 操作过,只做可见性
        ├── events.jsonl            ← task 时间线,只追加
        └── sessions/
            └── <session_id>/
                └── rounds.jsonl    ← agent 会话痕迹,只追加
```

## memory/(git)

- **一个决定一个 commit**。subject 的动词就是动作(`card: write` / `issue: argue` / `decide:` / `discuss:`),body 带 `Reason:` / `Task:` / `Rounds:`。
- **author** 来自 `MEMORY_TALK_AUTHOR` / `MEMORY_TALK_EMAIL`(默认 `memory.talk <memory.talk@localhost>`),用 `git -c` 传,不改仓库配置。
- **跨对象的决定落在同一个 commit**:`decide:` 同时动 `issues/<id>.json` 和 `cards/<id>.md`;`discuss:` 同理。
- **历史** = `git log -- <path>`;**检索** = `git grep -n -i -I`;**旧版本** = `git show <sha>:<path>`。都只用 git 命令行。
- **并发**:进程内一把锁串行化 `add + commit`。多进程写同一仓库不在 v5 范围内。
- **不进 git 的**:task 的一切。

## tasks/(裸文件)

- **原子写**:`task.json` / `canvas.json` / `sessions.json` / `members.json` 写临时文件后 `os.replace`。
- **只追加**:`events.jsonl` / `rounds.jsonl` 以 append 打开,从不改既有行。
- **单写者、无缓存直读**:服务进程是唯一写者;每次请求直接读盘。
- **不在 git 里**:画布重排、attach 时间、agent 的每一轮输出,都是过程,不是决定。
- **task 结束不删目录**:现场(tmux 会话)销毁,文件留着,可回去看痕迹。

## 运行时(不落盘)

| 东西 | 在哪 | 谁管 |
|---|---|---|
| tmux 会话(终端 / agent 现场) | tmux server,socket `-L <MEMORY_TALK_TMUX_SOCKET>`(默认 `memorytalk`) | server 层建 / 杀;会话名 = 会话 id |
| 各平台的会话记录(agent 把手读的原文) | `~/.claude/projects/` `~/.codex/sessions/` `~/.kimi-code/sessions/` | 各平台自己写;memory.talk 只读,按 cwd + 会话创建时间定位 |

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MEMORY_TALK_HOME` | `~/.memory.talk` | 根 |
| `MEMORY_TALK_AUTHOR` / `MEMORY_TALK_EMAIL` | `memory.talk` / `memory.talk@localhost` | git author |
| `MEMORY_TALK_WORKSPACE` | `~/workspace` | 终端类 URI 省略 path 时的 cwd |
| `MEMORY_TALK_TMUX_SOCKET` | `memorytalk` | tmux socket 名 |
| `MEMORY_TALK_TTYD_URL` | 无 | 终端那扇窗;不设则 `window.url = null` |
| `MEMORY_TALK_CLAUDE_PROJECTS` | `~/.claude/projects` | |
| `MEMORY_TALK_CODEX_SESSIONS` | `~/.codex/sessions` | |
| `MEMORY_TALK_KIMI_SESSIONS` | `~/.kimi-code/sessions` | |

没有配置文件。
