# memory.talk

> 跑 code agent 的工作台,记忆是它的副产物。

memory.talk v5 有三个顶层对象:

- **work** —— 做事。一件事是一个 work,复杂的事是一棵 work 树;每个 work 里盛放若干个现场(session):Claude Code / Codex / Kimi 会话、终端、网页,按 URI 打开,由对应的 work server 建出来,活得比连接久。
- **metas** —— 认知。一个分层的 git 仓库:`origin`(外部来的原文,只读)/ `issue`(问题 + 立场 + 论证,IBIS)/ `card`(争完的事实,维基式词条),还可以用一份 YAML schema 加自己的层。每个动作一个 `[层]` 提交,跨层被守卫拒绝;目录下的 `manager.json` 把变动打给某个 work 的收件箱。
- **user** —— 人。注册的实体,和 work 平级;work 谁建的、谁在动,metas 的提交谁做的。**不做权限**:一个实例给一个团队用。

**没有数据库、没有索引**:认知层在 git 里,work / user 的记录走可换的存储 provider(本地文件系统或 SQLite,将来 S3 / MySQL)。

设计文档见 [`docs/designs/v5/`](docs/designs/v5/README.md);数据结构 [`docs/structure/v5/`](docs/structure/v5/README.md);HTTP API [`docs/api/v5/`](docs/api/v5/README.md);CLI [`docs/cli/v5/`](docs/cli/v5/README.md)。

## 安装

```bash
pip install memorytalk
memory.talk server start          # 本地 API:http://127.0.0.1:8000/docs
```

需要 `git` 和 `tmux`(终端 / agent 现场跑在 tmux 里);要在浏览器里看终端再装 `ttyd`,并设 `MEMORY_TALK_TTYD_URL`。

## 用起来

```bash
memory.talk user add alice                                    # 注册(一次)
export MEMORY_TALK_USER=alice

W=$(memory.talk work create --goal '把配置改成环境变量' --json | jq -r .id)
memory.talk work attach $W codex:///home/alice/memory.talk    # 在 work 里开一个 Codex 会话
memory.talk work recall $W                                    # 开工注入:card 目录

memory.talk meta write issue memory.talk/配置/该走文件还是环境变量 --field question='配置该走文件还是环境变量?'
memory.talk meta act   issue position memory.talk/配置/该走文件还是环境变量 --field claim='只用环境变量'
memory.talk meta act   issue decide   memory.talk/配置/该走文件还是环境变量 \
    --field position=p1 --field card=memory.talk/配置/配置只来自环境变量
memory.talk work set $W --status done
```

## 存储

```
~/.memory.talk/
├── metas/     分层 git 仓库:layer/origin、layer/issue、layer/card(+ 用户层)、stack
├── works/           work 树、画布、会话、收件箱、round(MEMORY_TALK_STORE=fs 时)
└── users/           user 档案
```

`MEMORY_TALK_STORE=sqlite` 时 works / users 进 `memory.sqlite`;metas 永远是 git。全部环境变量见 [`docs/structure/v5/filesystem.md`](docs/structure/v5/filesystem.md)。

## 开发

```bash
pip install -e ".[dev]"
pytest                       # 每个场景在 fs 和 sqlite 两种 store 下各跑一遍
cd memorytalk/frontend && npm ci && npm run dev          # 前端(Vite + React;工作台 / 会话 / 认知库)
```

发布前先 `cd memorytalk/frontend && npm run build`(产物 `dist/` 随 wheel 分发),再 `python -m build && twine upload dist/*`。

## 布局

```
memorytalk/              ← Python 包(pip: memorytalk;命令 memory.talk)
├── cli/                 ← 命令行(本地 API 的客户端):server / work / user / meta 各一个文件
├── backend/             ← 服务:main.py config.py gateway.py
│   ├── models/ services/ controllers/     ← 三层
│   ├── providers/       ← 存储介质:FileSystemProvider(LocalFS)/ DatabaseProvider(SQLite)
│   ├── layers/          ← 内置 layer:origin / issue / card
│   └── work_servers/    ← 每个协议一个 work server:bash / claude / codex / kimi / http / default
└── frontend/            ← Vite + React 工作台(工作导航、会话、认知库、设置)
tests/                   ← 按场景组织
docs/                    ← designs / structure / api / cli
```

## License

[Apache License 2.0](LICENSE)
