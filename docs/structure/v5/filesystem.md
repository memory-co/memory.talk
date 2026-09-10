# Filesystem (v5)

`~/.memory.talk/` 下只有两样:一个分层 git 仓库,一堆裸文件。**没有数据库,没有索引**;每个字节都是 canonical。为什么见 [`../../designs/v5/store.md`](../../designs/v5/store.md)。

```
~/.memory.talk/                       ← MEMORY_TALK_HOME
├── collections/                      ← 分层 git 仓库(认知层),见 collections.md
│   ├── .git/                         ←   refs/heads/layer/{origin,issue,card,…}、refs/heads/stack;HEAD → stack
│   ├── layers                        ←   层清单,一行一层,最底在前(始祖提交里就有)
│   ├── schemas/<层>.yaml             ←   用户层的 schema(最底层)
│   ├── manager.json                  ←   根:管一切(可选)
│   └── <按主题组织的目录树>/          ←   原文、.issue/、.card/、.<用户层>/ 并排
│       ├── manager.json              ←   这一片归谁管(可选,任何目录)
│       ├── 某份原文.md                ←   origin:不带后缀的文件
│       ├── 某个问题.issue/            ←   issue:issue.json + 可选 manager.json + 附件
│       └── 某张卡.card/              ←   card:card.md + 可选 manager.json + 附件
├── works/                            ← 裸文件(现场层)
│   └── <work_id>/
│       ├── work.json                 ←   目标 / 父 / 状态
│       ├── canvas.json               ←   画布(视图);不存在 = 空画布
│       ├── sessions.json             ←   会话登记(数组,现场)
│       ├── members.json              ←   成员(人):谁在操作 / 操作过,只做可见性
│       ├── manager.json              ←   这棵子树的变动打给谁(可选;没有 → 父 work)
│       ├── events.jsonl              ←   work 时间线,只追加
│       ├── inbox.jsonl               ←   收件箱:manager.json 路由过来的变动,只追加
│       └── sessions/<session_id>/rounds.jsonl   ← agent 会话痕迹,只追加
└── unmanaged.jsonl                   ← 没人管的变动
```

## collections/(分层 git)

- **拓扑**:每层一条权威分支 `layer/<名>`(线性,只放这一层的文件);`stack` 是合并视图,每次层提交后一个 merge 节点。全部分支从始祖提交出发。工作树跟着 stack,只为了人能 `ls` / `cat`,服务从不读它。
- **一个动作一个 commit**,subject 以 `[层名]` 开头,动词在后(`write` / `edit` / `delete` / `position` / `argue` / `decide` / `manage` …),body 带 `Reason:` / `Task:`(哪个 work)/ `By:`(谁)/ `Decision:` / `Discussion:`。
- **守卫**在写时:路径按后缀 / 机制规则该归哪层、路径是否已在别的层的树里;不符即拒。跨层的决定是两个相邻提交。
- **author** 来自 `MEMORY_TALK_AUTHOR` / `MEMORY_TALK_EMAIL`,写进仓库 config。
- **历史** = `git log layer/<层>` / `git log --first-parent stack` / `git log -- <路径>`;**检索** = `git grep` stack;**旧版本** = `git show <sha>:<路径>`。只用 git 命令行。
- **并发**:进程内一把锁串行化提交。多进程写同一仓库不在 v5 范围内。
- **不进 git 的**:works/ 的一切。

## works/(裸文件)

- **原子写**:`work.json` / `canvas.json` / `sessions.json` / `members.json` / `manager.json` 写临时文件后 `os.replace`。
- **只追加**:`events.jsonl` / `inbox.jsonl` / `rounds.jsonl`,从不改既有行。
- **单写者、无缓存直读**:服务进程是唯一写者;每次请求直接读盘。
- **work 结束不删目录**:现场(tmux 会话)销毁,文件留着,可回去看痕迹。

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
| `MEMORY_TALK_CLAUDE_PROJECTS` / `MEMORY_TALK_CODEX_SESSIONS` / `MEMORY_TALK_KIMI_SESSIONS` | 各平台默认目录 | agent 会话记录根 |

没有配置文件。
