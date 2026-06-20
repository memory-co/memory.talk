# CLI Reference (v4)

## 一、v4 卡是什么

一张 v4 卡 = **一个 Issue(问题)+ 若干 Position(候选答案)**,卡连成一张被治理的问题图:

- **Card(问题)和 Position(答案)是两个对象**:**问题(卡)两个建法** —— `card create --issue '<问题>'` 显式建(如质疑另一问题),或 [`session mark`](session.md#session-mark) 的 `#…？` 在读 session 时自动建 / 关联;`card position --card <cid> --claim '<答案>'` 给已有问题加一个答案。
- 答案文本 `claim` 内联在 Position 上。
- 哪个答案胜出靠 `review` 顶/踩竞争;`credence`(质量分)由 `up/down` 计数**现算**、不落字段,无 `accepted` 标志。
- 卡↔卡用 IBIS 边(`card_links`)连图;**边是受治理对象**(有 `claim` / 顶踩 / 现算 credence / 证据 / 可 review,寻址 `card_…#l<n>`)。**三条出处链路分开**:card→session(哪条 mark 建/连了卡)落 `card_sessions`(经 mark);答案出处落 `position_sessions`(经 `indexes`,`card position --source` 写);边的出处落 `link_sessions`(经 `indexes`,`card link --source` 写)。
- 治理两条软约束:`scope`(一句话适用场景,软提示不挡)+ Position append-only(`forked_from` 记血缘)。

**本页是 CLI 契约;机制与设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md),写路径前端(逐 round 旁白标注)见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。**

## 二、命令树

```
memory.talk
├── setup                                       # 沿用 v3:交互式幂等安装 / 改配置 / 重启 / embedding 重算
├── server start | stop | restart | status      # 沿用 v3:本地 API 服务
├── sync start | stop | status                  # 沿用 v3:后端 watcher,实时落 session
├── card create | position | review | link  # v4:建问题(显式)/ 加答案 / 表态 / 连边;问题也可由 session mark 的 #…？ 自动建
├── read <id>                                    # v4:读 card_ / sess_(按前缀判型);card_…#p 读单个 Position、card_…#l 读单条 CardLink
├── search <query> [--where DSL]                # v4:撞问题检索(无沉浮,DSL 换计数字段)
├── recall --session <sid> --prompt '<p>'      # v4:hook 无意识召回,撞问题 → 取答案 → 注入
├── insight search | view                       # v4:v3 老卡改名(只读 + 搜索)
├── session list | tag                          # 沿用 v3:列 / 标 session
└── session mark --session <sid> [--mark <file>] # v4 新增:打注解(给 --mark=文件 / 不给=交互;#…？ 自动建卡)
```

**v4 重写 / 新增的命令**:`card`(create / position / review / link)/ `read` / `search` / `recall` / `insight` / `session mark`——卡的数据模型变了(问题 + 答案 + IBIS 边 + 出处),这些命令行为都跟 v3 不同;`session mark` 是 v4 抽卡的**写路径前端**(逐 round 打注解,机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md))。**沿用 v3 行为不变的基础设施**:`setup` / `server` / `sync` / `session list|tag`(本目录已完整收录各自的契约 doc);`explore`(抽 v4 卡的工作台)产物从 insight 卡换成 v4 卡。命令详情见 [#六、命令详情](#六命令详情)。

## 三、问题图 / 治理术语 → CLI 字段对照

| 术语 | 在 v4 里的落点 |
|---|---|
| Issue(问题) | `card`:`issue`(问题文本,检索锚点),一张卡 = 一个问题 |
| Position(候选答案) | `card position` 落的那个;`claim`(答案文本,内联) |
| 校验(对不对 / 边成不成立) | `card review --target <card#p<n>\|card#l<n>> --argument <+1/0/-1>`:`argument` 累成 target(Position 或 Link)的 `up_count` / `down_count` / `neutral_count` |
| credence(质量分) | **现算** `f(up, down)`(`up−down` / Wilson),不存字段(Position 和 Link 都没有);Position 排座次、Link 定去留 |
| 当下答案 | 召回时 credence 最高的 Position(平手按最近更新),**无 `accepted` 字段** |
| Argument(IBIS) | `argument ≠ 0` 的 review(顶 = pro / 踩 = con) |
| 问题图边(受治理) | `card_links`:`specializes` / `suggested_by` / `questions` / `replaces` / `related`;有 `claim` + 顶踩 + 现算 credence,寻址 `card_…#l<n>`,**存在即合理**(各边各自成立) |
| 出处:卡来自哪条 mark | `card_sessions`:card→session(经 **mark**),mark 写路径自动落,支持多条 |
| 出处:答案来自哪几轮 | `position_sessions`:position→session(经 **indexes**),`card position --source` 落,支持多 session |
| 出处:边从哪几轮观察 | `link_sessions`:link→session(经 **indexes**),`card link --source` 落,支持多 session |
| 位(适用场景) | `scope`:一句话软提示(非门禁,负边界写进文本) |
| 变(认知史) | Position **append-only** + `forked_from`(分叉血缘);旧答案不删,被踩则 credence 现算掉下去 |

**credence、当下答案、相关性都不是存字段**,是 `up/down/neutral_count` + 检索实时算出来的。

## 四、跟 v3 的差异

### 改名腾位

v3 那套卡(`insight` 字段 + 论坛 stats)**整体改名 `insight`**(数据保留、只读可搜、不再是抽卡主路径),把 `card` 这个名字 + `card_` 前缀腾给 v4。迁移见 [`../../works/v4/card.md`](../../works/v4/card.md#9-与-v3--insight-的共存与迁移)。`memory.talk insight` = 原 v3 `card` 改名而来。

### card 从"陈述"变"问答"

| | v3 `card` | v4 `card` |
|---|---|---|
| 一张卡是什么 | 一句 `insight`(陈述) | 一个 `issue`(问题)+ 若干 `Position`(答案) |
| 创建 | `card create '<json>'`(insight + rounds) | 建问题 `card create --issue '<Q>'`(显式)或 [`session mark`](session.md#session-mark) 的 `#…？`(从读 session);加答案 `card position --card <cid> --claim '<A>' [--source ...]` |
| 关联 | `source_cards`(card→card,创建即冻) | `card_links`(五类型 IBIS 边)+ `card_sessions`(card→session,经 mark)+ `position_sessions`(position→session,经 indexes) |
| 质量信号 | `stats`(6 计数器,**存**沉浮) | `up/down/neutral_count`(存计数)+ credence(**现算**) |
| 状态 | dormant/superseded 从动力学算 | 同样不存;且无 accepted、无 open/closed |

### review:target 从 card 改 Position / Link

`review` 沿用 v3 的"回帖"机制(`argument` ∈ +1/0/−1 + 证据 indexes),只把对象从整张卡**下放到 Position 或 CardLink**(`--target card#p<n>` / `card#l<n>`,前缀分片告诉 kind)——答案各自被顶踩竞争(择优),边各自被顶踩定去留(存在即合理)。`argument ≠ 0` 的 review 就是一条 IBIS Argument。

### recall:走问题图

`recall` 从"撞陈述"变"撞问题":context → 撞 `issue` → 取命中卡的 Position → 现算校验分排序(平手按最近更新)→ 连 `scope` 注入。

### 显式去掉(相对 v3 / 早期 v4 稿)

v4 不存这些:`accepted`、`momentum`/势、`TimeScope`/时、`change_state` 状态机 / `superseded_by`、结构化 `scope`(收成一句话文本)、`credence` 存储列——全部改读时现算或不建模。**删除理由见 [`../../works/v4/card.md`](../../works/v4/card.md) §3 / §5 / §12。**

## 五、典型工作流

### 第一次跑(沿用 v3)

```bash
memory.talk setup                # wizard
memory.talk server start         # 起后台 API
memory.talk sync start           # 后端 watcher,session 实时落库
```

### 日常读写(LLM 通过 tool-use 调)

```bash
# 1. 建一个新问题(显式;也可由 session mark 的 #…？ 从读 session 自动建)
memory.talk card create --issue '用户偏好什么回答风格?'

# 2. 给这个问题加第一个答案
memory.talk card position --card card_01jz8k2m --claim '默认简洁、要点优先' --source sess_abc:11-15

# 3. 再补一个竞争答案
memory.talk card position --card card_01jz8k2m --claim '调试场景下要详细、带完整命令' --source sess_def:3,7,12

# 4. 后续会话里对某个答案表态(顶 / 踩 / 中立)
memory.talk card review --target card_01jz8k2m#p1 --argument +1 --cite sess_ghi:20-25 --comment '又一次验证,简洁版接住了'

# 5. 看这张卡现在长什么样(所有答案 + 各自 credence)—— read 用位置参数
memory.talk read card_01jz8k2m

# 6. hook 阶段无意识召回
memory.talk recall --session sess_ghi --prompt '用户在问怎么写提交信息'
```

### 信念变了:加竞争答案 + 踩旧的

v4 不"改卡"也不"归档"——新增一个答案,踩旧答案,credence 自己把新的抬上来:

```bash
memory.talk card position --card card_01jz8k2m \
    --claim '其实用户要的是"可调档",默认简洁但一句话能展开' \
    --source sess_xyz:4-9
memory.talk card review --target card_01jz8k2m#p1 --argument -1 --cite sess_xyz:4-9 --comment '纯简洁漏了细节场景'
```

旧答案不删不改、仍在卡里可查;谁浮上来由 credence 现算说了算。认知史落在 reviews 日志 + 并存的旧 Position 上。

### 抽卡仍走 explore 工作台(行为沿用 v3)

在 explore 目录里逐 round 旁白标注,`#问题` 自动建卡 / 关联;产物从"insight 卡"换成"v4 卡(问题 + 答案)"。命令契约见 [explore.md](explore.md),写路径机制见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。

## 六、命令详情

| 命令 | 文档 |
|---|---|
| `card`(create / position / review / link) | [card.md](card.md) |
| `read` | [read.md](read.md) |
| `search` | [search.md](search.md) |
| `recall` | [recall.md](recall.md) |
| `insight`(search / view,只读) | [insight.md](insight.md) |
| `session`(list / tag 沿用 v3 + **mark v4 新增**) | [session.md](session.md) |
| `setup`(沿用 v3) | [setup.md](setup.md) |
| `server`(沿用 v3,无独立 doc;起停 / 重启见 setup) | [setup.md](setup.md) |
| `sync`(沿用 v3;端点 `/v3`→`/v4`) | [sync.md](sync.md) |
| `upgrade`(沿用 v3) | [upgrade.md](upgrade.md) |
| `explore`(抽 v4 卡工作台;产物换 v4 卡) | [explore.md](explore.md) |

> 数据结构 / schema 见 [`../../structure/v4/`](../../structure/v4/);HTTP API 见 [`../../api/v4/`](../../api/v4/);**机制 / 设计决策** 见 [`../../works/v4/card.md`](../../works/v4/card.md)。

## 七、设计原则

1. **Python 不调 LLM API**:认知工作走 Skill / agent;CLI 只做机械数据操作(沿用 v3 的 `CLAUDE.md` 约束)。
2. **CLI 命令 = 一次机械操作**:一个命令一件事,Markdown 默认输出、`--json` 备选,人 / agent 都好处理。
3. **答案(Position)append-only**:`claim` 创建即冻结。评价走 `review`,改主意走"新增竞争 Position + 踩旧的",不改老答案。
4. **状态从计数现算,不存字段**:没有 `credence` / `accepted` / `state` 列;质量、当下答案、相关性都从 `up/down/neutral_count` + 检索实时算。

第 3 / 第 4 条联合保证:**问题图的 lineage 自然成 DAG**(append-only + 边只指向已存在节点),系统不做环检测。
