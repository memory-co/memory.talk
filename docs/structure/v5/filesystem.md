# Filesystem (v5)

`~/.memory.talk/` 下主要是三样:一个分层 git 仓库(认知层,每个字节都是 canonical,为什么见 [`../../designs/v5/metas/store.md`](../../designs/v5/metas/store.md));work 的两个 sqlite——`works.db`(现在)和 `worktrace.db`(经过),见 [`../../designs/v5/work-store.md`](../../designs/v5/work-store.md);users / auth 的记录(按 `MEMORY_TALK_STORE` 是裸文件或 `memory.sqlite`)。

```
~/.memory.talk/                       ← MEMORY_TALK_HOME
├── metas/                      ← 分层 git 仓库(认知层),见 metas.md
│   ├── .git/                         ←   refs/heads/layer/{origin,issue,card,…}、refs/heads/stack;HEAD → stack
│   ├── metas.json              ←   锚定:整个 metas 的配置 + layers[](最底在前,只有名字和 builtin);始祖提交只有它;git 历史 = 层的变化史
│   ├── manager.json                  ←   根:管一切(可选)
│   └── <按主题组织的目录树>/          ←   原文、.issue/、.card/、.<用户层>/ 并排
│       ├── manager.json              ←   这一片归谁管(可选,任何目录)
│       ├── 某份原文.md                ←   origin:不带后缀的文件
│       ├── 某个问题.issue/            ←   issue:readme.md + positions/<主张>.md(每个文件 = frontmatter 字段 + 正文)+ 可选 manager.json
│       └── 某张卡.card/              ←   card:readme.md(字段 context / links / issue + 正文)+ 可选 manager.json
├── layers/                           ← 用户自定义层:<名>.yaml 各一份协议,启动时载入(和内置层一模一样)
├── users/                            ← user 档案(注册的实体;MEMORY_TALK_STORE=fs 时)
│   └── <name>.json                   ←   name / display_name / email / created_at / role / password(scrypt 哈希,不出接口)
├── jwt.key                           ← 签 JWT 的密钥(首次启动生成,0600;换掉 = 全员重新登录)
├── auth/tokens/<sha256>.json         ← 登录态登记:JWT 里 jti 的哈希 → {user, created_at, exp}(logout / 改密码即删)
├── tmuxd/                            ← tmuxd 的 state(会话记录、ttyd 记录、tmux.conf、ttyd.sock——窗经它挂到 /surface/tmuxd);tmux 会话本身不落盘
├── center.sock                       ← 中心给本机节点开的口子(0600;从这里上来的请求身份是节点,只能读写 trace)
├── node/                             ← 本机节点(memory.talk node):node.sock(中心 → 节点)、node.json、node.log
│   └── worklets/<worklet id>/        ←   盯着的工作单元:watch.json(盯它的说明)、hooks.jsonl(事件)、settings.json(claude 的 hooks)、bashrc + cur + out/(bash 记命令的钩子、正在跑的那条、每条命令的输出)
├── credentials.json                  ← CLI 的登录态(客户端的事,按服务地址分开;memory.talk login 写)
├── works.db                          ← work 的现在(sqlite,+ -wal / -shm):works / work_columns / worklets / inbox 四张表
├── worktrace.db                      ← work 的经过(sqlite,+ -wal / -shm):spans / points / trace_cursors 三张表
└── memory.sqlite                     ← users / auth(只在 MEMORY_TALK_STORE=sqlite 时)
```

## metas/(分层 git)

- **拓扑**:每层一条权威分支 `layer/<名>`(线性,只放这一层的文件);`stack` 是合并视图,每次层提交后一个 merge 节点。全部分支从始祖提交出发。工作树跟着 stack,只为了人能 `ls` / `cat`,服务从不读它。
- **一个动作一个 commit**,subject 以 `[层名]` 开头,动词在后(默认 `write` / `edit` / `delete` / `manage`;调用方可自己给主题,如 `position …` / `argue …` / `rank …`),body 带 `Reason:` / `Work:`(哪个 work);谁 = commit author。
- **守卫**在写时:路径按后缀 / 机制规则该归哪层、路径是否已在别的层的树里;不符即拒。跨层的决定是两个相邻提交。
- **author** 来自 `MEMORY_TALK_AUTHOR` / `MEMORY_TALK_EMAIL`,写进仓库 config。
- **历史** = `git log layer/<层>` / `git log --first-parent stack` / `git log -- <路径>`;**检索** = `git grep` stack;**旧版本** = `git show <sha>:<路径>`。只用 git 命令行。
- **并发**:进程内一把锁串行化提交。多进程写同一仓库不在 v5 范围内。
- **不进 git 的**:works.db / worktrace.db 的一切。

## works.db / worktrace.db(work 固定是 sqlite)

表和列见 [work.md](work.md) 和 [designs work-store.md §3–§5](../../designs/v5/work-store.md);`worktrace.db` 三张表的逐列设计见 [worktrace.md](worktrace.md)。

| 库 | 表 | 一行是 |
|---|---|---|
| `works.db` | `works` | 一个 work:`parent` 就是树;`manager`(这棵子树的变动打给谁,空 = 父 work)、`viewers`(现在谁在看,心跳算出来整份写,重启清空)、计数器 `next_worklet` / `next_column` |
| | `work_columns` | 一列,主键 (`work_id`, `number`),`position` 从左到右 0..n-1 |
| | `worklets` | 一个工作单元:登记 + 摆在哪一列第几个(`column_number` / `position` / `collapsed`) |
| | `inbox` | 一条打过来的变动;`work_id` 为空 = 没人管 |
| `worktrace.db` | `spans` | 一个段(`work` / `worklet` / `agent.session` / `agent.turn` / `agent.tool`),终点为空 = 还开着 |
| | `points` | 一个点:人的动作(`column.*` / `worklet.*` / `work.renamed`),或 agent 的一条消息 / 状态(`agent.*`,正文在 `body`);只追加,带 `uid` 的按它去重 |
| | `trace_cursors` | 一个工作单元一份来源推到哪了;和推上来的数据同一个事务写 |

- **一个动作一个事务**:一个动作在 `works.db` 里的读-改-写在一个事务里做完;建 / 销毁现场不在事务里;最后写 `worktrace.db`。两个库之间没有原子提交,轨迹写失败只记日志,不回滚 work。
- **单写者**:服务进程是唯一写者,每个库一个 provider 实例、一把进程内锁;CLI 和 agent 都走 HTTP。
- **work 归档不删记录**:现场(tmux 会话)销毁,登记和列(连同每个工作单元摆在哪)留着,可回去看痕迹。
- users / auth 仍按 `MEMORY_TALK_STORE`:`fs` 时是上面的 `users/` / `auth/tokens/`,`sqlite` 时在 `memory.sqlite`(`MEMORY_TALK_SQLITE` 可改路径)的 `users` / `auth_tokens` 表里,业务层不感知(见 [designs provider.md](../../designs/v5/provider.md))。

## 运行时(不落盘)

| 东西 | 在哪 | 谁管 |
|---|---|---|
| tmux 会话(终端 / agent 现场) | tmuxd 的 tmux server,socket `tmuxd-<MEMORY_TALK_TMUX_SOCKET>`;ttyd 是 memory.talk 的子进程 | server 层经 tmuxd 建 / 杀;会话名 = 工作单元 id;state 在 `<home>/tmuxd/` |
| 各平台的会话记录(agent 的原文) | `~/.claude/projects/` `~/.codex/sessions/` `~/.kimi-code/sessions/` | 各平台自己写;memory.talk 只读。Claude Code 由节点按开现场时钉住的会话 id 找(`*/<会话 id>.jsonl`),读了推进 trace;Codex / Kimi 还是中心按 cwd + 工作单元创建时间定位(旧路径) |

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MEMORY_TALK_HOME` | `~/.memory.talk` | 根 |
| `MEMORY_TALK_STORE` | `fs` | users / auth 记录的介质:`fs` / `sqlite`(work 不看它) |
| `MEMORY_TALK_SQLITE` | `<HOME>/memory.sqlite` | users / auth 的 sqlite 文件路径 |
| `MEMORY_TALK_WORKS_DB` | `<HOME>/works.db` | work 的现在 |
| `MEMORY_TALK_WORKTRACE_DB` | `<HOME>/worktrace.db` | work 的经过(段、点) |
| `MEMORY_TALK_AUTHOR` / `MEMORY_TALK_EMAIL` | `memory.talk` / `memory.talk@localhost` | git author |
| `MEMORY_TALK_WORKSPACE` | `~/workspace` | 终端类 URI 省略 path 时的 cwd |
| `MEMORY_TALK_TMUX_SOCKET` | `memorytalk` | tmuxd 的 socket 名(实际 tmux socket 是 `tmuxd-<名>`),和你自己的 tmux 隔离 |
| `MEMORY_TALK_CLAUDE_PROJECTS` / `MEMORY_TALK_CODEX_SESSIONS` / `MEMORY_TALK_KIMI_SESSIONS` | 各平台默认目录 | agent 会话记录根 |

没有配置文件。
