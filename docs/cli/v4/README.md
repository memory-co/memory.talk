# CLI Reference (v4)

## 一、设计立场:记忆是被治理的问题图,不是论坛帖墙

v3 把记忆当成**一个内部论坛**:每张 card 是一个帖子(一句 `insight`),靠 review 顶/踩沉浮。它解决了"记忆会自我演化"的问题,但卡仍是**孤立陈述**——两张卡互相矛盾时(「用户喜欢简洁」vs「用户有时要详细」)谁说了算,系统没有结构。

v4 把卡升级成**一个问题 + 它的若干答案**,所有卡连成一张**被治理的问题图**:

- 一张卡 = **一个 Issue(问题)**,底下挂 **若干 Position(候选答案)**;
- 哪个答案胜出,不靠创建时拍板,而是后面用 **review 顶/踩** 竞争出来(`credence` = 顶踩计数现算的校验分);
- 卡与卡之间用 **IBIS 边**(`card_links`)连成图(细化 / 取代 / 质疑 / 引出 / 泛关联);
- 每个答案的**出处**(哪个 session 的哪几轮旁白启发了它)落在 **`card_sessions`** 关系表;
- 治理只剩两条**软**约束:**位**(`scope`,一句话适用场景描述,软提示不挡)+ **变**(Position append-only、`forked_from_position_id` 记血缘)。

机制 / 设计推理见 [`../../works/v4/card.md`](../../works/v4/card.md);写路径前端(逐 round 旁白标注)见 [`../../works/v4/session-annotation.md`](../../works/v4/session-annotation.md)。

### 三个核心思想,落到了 CLI 里

**1. 问答化(card = 问题 + 答案)**

与其存陈述「用户喜欢简洁」,不如存「用户偏好什么回答风格?」这个**问题**,底下挂上候选答案。问题是天然的索引(检索时拿 context 撞问题),也天然容纳竞争——同一个问题可以有多个答案各自被顶踩。`card create` 因此分两件事:给不给 `--card` 决定**建新问题**还是**给老问题加答案**。

**2. credence 是现算的校验分,不是存的字段**

每个 Position 只存三个计数:`up_count`(顶)/ `down_count`(踩)/ `neutral_count`(中立)。`credence` **不落字段**,是排序那一刻按 `f(up, down)` 现算的质量分(`up−down`,或带样本量的 Wilson 下界)。「当下用哪个答案」= credence 最高的那个,**不设 `accepted` 标志、不钉 open/closed**——一个问题本就允许多个答案长期并存竞争。

**3. 相关性只在召回时算,治理是软提示**

「这个答案现在相不相关」不回写任何字段,而是**召回那一刻**由检索(撞问题)现算。`scope` 不是门禁——它是一句**适用场景描述**,随答案一起喂给 LLM 当软提示,跨界默认放行,只在文本里写明的负边界上提醒。这跟"记忆的价值在跨界"是一致的。

## 二、命令树

```
memory.talk
├── setup                                       # 沿用 v3:交互式幂等安装 / 改配置 / 重启 / embedding 重算
├── server start | stop | restart | status      # 沿用 v3:本地 API 服务
├── sync start | stop | status                  # 沿用 v3:后端 watcher,实时落 session
├── card create | view                          # v4:建问题 / 给问题加答案;看一张卡的所有答案
├── review <position_id> <+1|0|-1> --cite ...    # v4:对某个答案(Position)表态
├── recall <session_id> <prompt>                # v4:无意识召回,撞问题 → 取答案 → 注入
├── read <id>                                    # 沿用 v3:读 card 或 session(按前缀判型)
├── search <query> [--where DSL]                # 沿用 v3:有意识检索
├── session list | tag                          # 沿用 v3:列 / 标 session
└── insight ...                                  # v3 卡改名而来(只读 + 搜索),见 §四
```

**v4 只重写卡子系统(`card` / `review` / `recall`)**;`setup` / `server` / `sync` / `read` / `search` / `session` / `explore` 沿用 v3 契约不变(见 [`../v3/`](../v3/)),本目录不复制。`card` 命令详情见 [#六、命令详情](#六命令详情)。

## 三、问题图 / 治理术语 → CLI 字段对照

| 术语 | 在 v4 里的落点 |
|---|---|
| Issue(问题) | `card`:`issue`(问题文本,检索锚点),一张卡 = 一个问题 |
| Position(候选答案) | `card create --answer` 落的那个;`claim`(答案文本,内联) |
| 校验(对不对) | `review <pid> <+1/0/-1>`:`argument` 累成 `up_count` / `down_count` / `neutral_count` |
| credence(质量分) | **现算** `f(up, down)`(`up−down` / Wilson),不存字段;排序用 |
| 当下答案 | 召回时 credence 最高的 Position(平手按最近更新),**无 `accepted` 字段** |
| Argument(IBIS) | `argument ≠ 0` 的 review(顶 = pro / 踩 = con) |
| 问题图边 | `card_links`:`specializes` / `suggested_by` / `questions` / `replaces` / `related` |
| 出处(谁启发的) | `card_sessions`:card↔session,`--cite` 落,支持多 session |
| 位(适用场景) | `scope`:一句话软提示(非门禁,负边界写进文本) |
| 变(认知史) | Position **append-only** + `forked_from_position_id`(分叉血缘);旧答案不删,被踩则 credence 现算掉下去 |

**credence、当下答案、相关性都不是存字段**,是计数 + 检索实时算出来的。v4 不做状态机迁移,只让计数说话。

## 四、跟 v3 的差异

### 改名腾位

v3 那套卡(`insight` 字段 + 论坛 stats)**整体改名 `insight`**(数据保留、只读可搜、不再是抽卡主路径),把 `card` 这个名字 + `card_` 前缀腾给 v4。迁移见 [`../../works/v4/card.md`](../../works/v4/card.md#9-与-v3--insight-的共存与迁移)。`memory.talk insight` = 原 v3 `card` 改名而来。

### card 从"陈述"变"问答"

| | v3 `card` | v4 `card` |
|---|---|---|
| 一张卡是什么 | 一句 `insight`(陈述) | 一个 `issue`(问题)+ 若干 `Position`(答案) |
| 创建 | `card create '<json>'`(insight + rounds) | `card create (--card\|--issue) --answer [--cite ...]` |
| 关联 | `source_cards`(card→card,创建即冻) | `card_links`(五类型 IBIS 边)+ `card_sessions`(出处) |
| 质量信号 | `stats`(6 计数器,**存**沉浮) | `up/down/neutral_count`(存计数)+ credence(**现算**) |
| 状态 | dormant/superseded 从动力学算 | 同样不存;且无 accepted、无 open/closed |

### review:target 从 card 改 Position

`review` 沿用 v3 的"回帖"机制(`argument` ∈ +1/0/−1 + 证据 indexes),只把对象从整张卡**下放到 Position**——同一问题下的不同答案各自被顶踩、各自竞争。`argument ≠ 0` 的 review 就是一条 IBIS Argument。

### recall:走问题图

`recall` 从"撞陈述"变"撞问题":context → 撞 `issue` → 取命中卡的 Position → 现算校验分排序(平手按最近更新)→ 连 `scope` 注入。

### 显式去掉(相对 v3 / 早期 v4 稿)

| 概念 | 为什么不要 |
|---|---|
| `accepted` 字段 | 纯派生(=credence 最高),且钉"已解决"违背 IBIS;改读时现算 |
| `momentum` / 势 | recall/read 回写是冗余(相关性召回时检索现算),还污染"被验证过" |
| `TimeScope` / 时 | 过期暂不建模(见 [card.md §12](../../works/v4/card.md));过期靠后续被踩压 credence |
| `change_state` 状态机 / `superseded_by` | "不覆盖"靠 Position append-only,"停用"靠 credence 现算掉下去 |
| 结构化 `scope`(域×角色×权限×层) | 收成一句话自由文本软提示;预防性门禁与"跨界是价值"冲突 |
| `credence` / `accepted` 存储列 | 全部读时现算,只存原始计数 |

## 五、典型工作流

### 第一次跑(沿用 v3)

```bash
memory.talk setup                # wizard
memory.talk server start         # 起后台 API
memory.talk sync start           # 后端 watcher,session 实时落库
```

### 日常读写(LLM 通过 tool-use 调)

```bash
# 1. 冒出一个新问题,并给出第一个答案
memory.talk card create \
    --issue '用户偏好什么回答风格?' \
    --answer '默认简洁、要点优先' \
    --cite sess_abc:11-15

# 2. 给已有问题补一个竞争答案
memory.talk card create \
    --card card_01jz8k2m \
    --answer '调试场景下要详细、带完整命令' \
    --cite sess_def:3,7,12

# 3. 后续会话里对某个答案表态(顶 / 踩 / 中立)
memory.talk review pos_01jzr5kq +1 --cite sess_ghi:20-25 --comment '又一次验证,简洁版接住了'

# 4. 看这张卡现在长什么样(所有答案 + 各自 credence)
memory.talk card view card_01jz8k2m

# 5. hook 阶段无意识召回
memory.talk recall sess_ghi '用户在问怎么写提交信息'
```

### 信念变了:加竞争答案 + 踩旧的

v4 不"改卡"也不"归档"——新增一个答案,踩旧答案,credence 自己把新的抬上来:

```bash
memory.talk card create --card card_01jz8k2m \
    --answer '其实用户要的是"可调档",默认简洁但一句话能展开' \
    --cite sess_xyz:4-9
memory.talk review pos_OLD -1 --cite sess_xyz:4-9 --comment '纯简洁漏了细节场景'
```

旧答案不删不改、仍在卡里可查;谁浮上来由 credence 现算说了算。认知史落在 reviews 日志 + 并存的旧 Position 上。

### 抽卡仍走 explore 工作台(沿用 v3)

在 explore 目录里逐 round 旁白标注,`#问题` 自动建卡 / 关联;产物从"insight 卡"换成"v4 卡(问题 + 答案)"。机制见 [`../v3/explore.md`](../v3/explore.md) 与 [`../../works/v4/session-annotation.md`](../../works/v4/session-annotation.md)。

## 六、命令详情

| 命令 | 文档 |
|---|---|
| `card` | [card.md](card.md) |
| `review` | [review.md](review.md) |
| `recall` | [recall.md](recall.md) |
| `setup` / `server` / `sync` / `read` / `search` / `session` / `explore` | 沿用 v3,见 [`../v3/`](../v3/) |
| `insight` | v3 `card` 改名而来(只读 + 搜索为主) |

> 数据结构 / schema 见 [`../../structure/v4/`](../../structure/v4/);HTTP API 见 [`../../api/v4/`](../../api/v4/);**机制 / 设计决策** 见 [`../../works/v4/card.md`](../../works/v4/card.md)。

## 七、设计原则

1. **Python 不调 LLM API**:认知工作走 Skill / agent;CLI 只做机械数据操作(沿用 v3 的 `CLAUDE.md` 约束)。
2. **CLI 命令 = 一次机械操作**:一个命令一件事,Markdown 默认输出、`--json` 备选,人 / agent 都好处理。
3. **答案(Position)append-only**:`claim` 创建即冻结。评价走 `review`,改主意走"新增竞争 Position + 踩旧的",不改老答案。
4. **状态从计数现算,不存字段**:没有 `credence` / `accepted` / `state` 列;质量、当下答案、相关性都从 `up/down/neutral_count` + 检索实时算。v4 比 v3 更彻底——v3 还存 stats,v4 连 credence 都不存。

第 3 / 第 4 条联合保证:**问题图的 lineage 自然成 DAG**(append-only + 边只指向已存在节点),系统不做环检测。
