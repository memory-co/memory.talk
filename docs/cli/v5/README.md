# CLI Reference (v5)

`memory.talk` 命令行是本地 API(`/api/…`)的客户端:**CLI 不含业务逻辑**,每条命令对应一个或几个端点(响应信封 `{data, message}` 由 CLI 解开,`--json` 输出的是 `data`)。机制见 [`../../designs/v5/`](../../designs/v5/README.md),端点见 [`../../api/v5/`](../../api/v5/README.md)。

> **状态:契约稿,未实施。** v5 的 CLI 重写,不沿用 v3 / v4 的任何命令(`card` / `insight` / `sync` / `explore` 都退役)。

## 一、命令树

```
memory.talk
├── version                                             # 版本号(也可 -V / --version)
├── server   start | stop | restart | status          # 本地 API 服务(后台守护)
├── work     create | list | show | set               # work 树
│            attach | sessions | detach | capture | rounds   # 会话(现场)
│            inbox | manager | users | touch           # 收件箱 / manager / user
│            servers                                    # 有哪些 work server(bash / claude / codex / kimi / http / default)及各自响应的协议
├── user     add | list | show | set | whoami           # 人:注册的实体,和 work 平级;不做权限
├── collection                                          # 认知层(API 是 /api/collections)
│            layers | tree | search
│            read | write | edit | rm | log             # 对象 CRUD + 历史
│            manager | managed                          # manager.json

```

**命令组名用单数**(`work` / `collection`),像 `docker container`;它们操作的是 API 里的复数资源(`/api/works` / `/api/collections`)。`col` 是 `collection` 的别名。

分页面:[server.md](server.md) · [work.md](work.md) · [user.md](user.md) · [collection.md](collection.md)

## 二、全局约定

| 全局 flag | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `--server <url>` | `MEMORY_TALK_SERVER` | `http://127.0.0.1:8000` | API 在哪 |
| `--user <名字>` | `MEMORY_TALK_USER` | 无 | **我是谁**:进 `X-Memory-Talk-User`,**必须是 `user add` 注册过的名字**(否则 exit 1)。建 work 时写进 `created_by`,动 work 时记进 users,collection 的提交以它为 author(名字 + 档案里的邮箱)。不带照样能用,只是匿名 |
| `--work <id>` | `MEMORY_TALK_WORK` | 无 | **在哪个 work 里操作**:进 `X-Memory-Talk-Work`。自己造成的变动不投给自己的收件箱。agent 会话由 work 拉起时,这个变量已经在它的环境里 |
| `--json` | — | 关 | 结构化输出(机器 / LLM 用);默认 Markdown,TTY 下用 rich 渲染 |

- **参数风格**:主对象用位置参数(`work show <id>`、`collection read <layer> <path>`),其余一律命名 flag(`--xx`)。
- **文本传文件 / stdin**:所有文本类 flag(`--goal` `--reason` `--content` `--put 文件=内容` 的值)支持 `@<file>`(逐字节原样读)和 `@-`(stdin,一条命令只能出现一次),给带引号、换行、`$` 的内容用。
- **退出码**:`0` 成功;`1` 业务错误(API 4xx,stderr 打 `**error:** <message>`,`--json` 时 stdout 打错误体);`2` 用法错误;`3` 连不上 server(提示 `memory.talk server start`)。
- **id 与路径**:work 是 `work_…`;会话是 `<work_id>-s<n>`;collection 对象是**路径**(`memory.talk/配置/该走文件还是环境变量`),直接当位置参数,不用引号也行,有空格才引。

## 三、典型一天

```bash
memory.talk server start                                     # 起服务(一次)
memory.talk user add alice --email alice@example.com         # 注册(一次)
export MEMORY_TALK_USER=alice
W=$(memory.talk work create --goal '把配置改成环境变量' --json | jq -r .id)
memory.talk work attach $W codex:///home/alice/memory.talk   # 在这个 work 里开一个 Codex 会话,打印窗地址
memory.talk collection write issue memory.talk/配置/该走文件还是环境变量 --put readme.md='起服务要读几样配置……'
memory.talk collection edit  issue memory.talk/配置/该走文件还是环境变量 --put positions/只用环境变量.md=@立场.md --subject 'position …: 只用环境变量'   # frontmatter 里 rank / verdict
memory.talk collection write card memory.talk/配置/配置只来自环境变量 --put readme.md=@卡.md                                     # frontmatter 里 issue: <那个 issue 的 path>
memory.talk work set $W --status done
```
