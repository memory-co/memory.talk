# CLI Reference (v3)

## 一、设计立场:记忆是论坛,不是仓库

v3 在工程上跟 v2 相似 —— 本地 server + CLI + hybrid FTS/向量检索。差别在**对"记忆"的隐喻**:

主流 memory 系统(含 v2)把记忆当成**一个仓库** —— 能存、能取、能搜。议题是检索效率、存储成本、schema 设计。

v3 把记忆当成**一个内部论坛**:每张 card 是一个**帖子**,带核心主张和它隐含的可证伪预测;每次后续会话是一条**回帖**,带 ±1 / 0 的 score 和 comment。整个系统不是被人维护的,是自己在演化 —— 跟 Reddit / HackerNews / 知乎运营动力学同构。

### 四个核心论坛动力学,落到了 CLI 里

**1. 沉浮(rising / sinking)**

帖子在论坛里有个隐含的"位置" —— 列表里靠前还是靠后、能不能被搜到、推送还是埋。这个位置不是设计的,是**论坛自带的动力学**算出来的:Reddit hot 算法、HackerNews 衰减公式、BBS 的置顶 / 沉底,都是同一套基本规则的方言 —— 有人回帖被翻起来、被赞可信度上升、被踩进待审区、长期没人理慢慢沉底。

v3 让 search 默认按一个**沉浮公式**排序,变量是 `review_up` / `review_down` / `read_count` / `recall_count` / `age_days`。公式配在 settings,不写死。一张 card 浮起来还是沉下去,看这些信号自己说话,不靠任何人手动打 "hot" / "dormant" 标签。

**2. Fork(分叉,不是替换)**

老帖被反驳到一定程度,不会被改写 —— 系统**开一个新帖**,链回老帖。老帖位置可能变 dormant 但**保留可检索**,因为世界可能变回去,老观点也可能复活。

v3 的 card 是**严格 append-only**:`insight` / `rounds` / `source_cards` 创建即冻结,不接受修改。要"翻新一张 card",新建一张,在 `source_cards` 里挂 `relation: "supersedes"` 指回老 card。新老两边都继续接收 review,谁活下来由沉浮排序说了算 —— 系统不强行把老 card 打成 dormant。

这种"不删不改、新老并存"的姿态对**避免锁死在错误的转弯**很关键。删帖 / 改帖会把判断错的成本永久化;append-only + 动力学沉浮则给老观点复活的可能。

**3. 真讨论 vs 路过(两种不同的参与)**

普通论坛把这两种混着算 engagement,但在 agent 内部**必须分开**:

- **真讨论**:点赞、点踩、写有态度的回复(在 v3 里 = `review`,带 score)。**认知层的支撑** —— 这个观点经历过几次真表态。
- **路过**:浏览、引用、纯水回复(在 v3 里 = `read` / `recall`)。**操作层的存在感** —— 这个观点常被翻出来用,但不一定真被检验过。

两者通常相关,但**会严重错位**:一张被狂用但没人真讨论过的 card 看起来很稳,其实是 shadow knowledge(下一条)。所以 v3 的 `card.stats` 把这两类分开:`review_up` / `review_down` / `review_neutral` / `review_count` 是真讨论;`read_count` / `recall_count` 是路过。沉浮公式只吃 review,不吃 read —— 被自动召回 ≠ 被人主动用过。

**4. Shadow knowledge(高路过低讨论的 card)**

**最危险的不是错的 card,而是从未被检验过的 card**。错的 card 会被踩、被 fork、沉到归档;未经讨论的 card 不会沉 —— 它们用得很多,看起来很稳,每次出场都没被真正测试。系统在默默依赖一个从未被挑战过的假设。

诊断它很简单 —— 找 **`read_count + recall_count` 高但 `review_count` 低**的 card。v3 用 DSL 一行查出来:

```bash
memory-talk search "" -w 'read_count + recall_count > 10 AND review_count = 0'
```

拿到这批 card 之后,agent 在合适时机主动 surface 给用户做 calibration check(active grounding) —— 把容易出错的 card 主动暴露到用户视野里,让人在场地纠正比让系统猜要靠谱。

### 这套机制理论上有迹可循

把上面 4 条合起来,整个机制可以一句话概括:

> **让没人讨论的帖子重新被讨论,让被反驳的帖子被分叉,让陈旧无用的帖子安静沉底,让经过多次确认的精华帖稳定在被引用的位置。**

这跟 Friston 的 variational free energy(神经系统持续做一件事:让自己越来越少被外界"惊讶")在数学结构上同构;艾宾浩斯遗忘曲线 `R ≈ e^(-t/S)`、ACT-R 的 `activation = log(Σᵢ tᵢ^(-d))`、Reddit hot 算法 —— 都是同一套底层模式在不同 substrate 上的实现。

**遗忘是功能,不是 bug**:健康的 memory 系统**必须会遗忘**,否则陈年错误获得了和新证据同等的发言权。"什么都记"的系统跑长了之后必然幻觉化 —— 这是结构性问题,不是 prompt 调优能解决的。

v3 不重新发明物理学,直接照搬几十年验证过的论坛运营常识。

### 最终一个健康的 agent 内部论坛长这样

少数核心精华帖像恒星一样稳定,被反复引用、反复确认;外围是大量短命的、不断生灭的猜测帖;中间是正在被讨论、不断 fork 的争议帖。整个系统在沉浮动力学里**自动调节自己的形态**。

工程师能做的不是设计每一张 card,**是把这套论坛的运行规则搭好,然后让它自己长**。所谓"养成"不是给 agent 灌输什么,是让这套论坛动力学自己跑起来。Agent 的人格、价值观、偏好,不是被设计的,是从底层 raw 一路结晶上来的精华帖。

## 二、命令树

```
memory-talk
├── setup                                       # 交互式幂等安装 / 改配置 / 重启 / embedding 重算
├── server start | stop | status                # 本地 API 服务(沿用 v2 契约,后续补 v3 文档)
├── sync start | stop | status                  # 后端 watchdog,实时把 Claude Code session 落到 backend
├── card '<json>'                               # 写一张帖子(card,immutable,append-only)
├── review '<json>'                             # 对某张 card 回帖(score + comment,挂单 session 一段 indexes)
├── read <id>                                   # 读 card 或 session(按 id 前缀自动判型)
├── search <query> [--where DSL]                # 有意识检索:沉浮公式排序
└── recall <session_id> <prompt>                # 无意识召回:hook 阶段极简 cards 注入 LLM context
```

每个命令一份独立文档,见 [#六、命令详情](#六命令详情)。

## 三、论坛动力学 → CLI 字段对照

| 论坛术语 | 在 v3 里的落点 |
|---|---|
| 主帖 | `card`:`insight`(核心主张) + `rounds`(来自 session 的证据) + `source_cards`(引用的更早 card) |
| 回帖 + 态度 | `review`:`score ∈ {1, 0, -1}` + `comment`,挂某 session 一段 `indexes` 作证据 |
| 楼层 / 转贴关系 | `card.source_cards[]`:带 `relation`(`derives_from` / `supersedes`),创建时确定**不可改** |
| 沉浮位置 | `search` 默认按沉浮公式排序(变量:relevance / review_up / review_down / read_count / recall_count / age_days),公式配在 `settings.search.ranking_formula` |
| 真讨论 vs 路过 | `card.stats.review_*`(真讨论)vs `card.stats.read_count` + `recall_count`(路过) |
| Fork | 新 card 的 `source_cards` 挂 `relation: "supersedes"` 指回老 card;老卡不删不改,谁活下来由动力学说了算 |
| Shadow 帖 surface | DSL 查询:`search "" -w 'read_count > 10 AND review_count = 0'` |
| 复活 | 不需要命令 —— 老 card 永远在,后续 review 把它捧起来即可 |

**沉浮、dormant、superseded 都不是存字段**,而是 stats + 关系图实时算出来的位置。v3 系统不做"状态机迁移",只让动力学跑。

## 四、跟 v2 的差异

### 新增

| | 作用 |
|---|---|
| `review` 命令 | 给 card 回帖,带 score + comment,是 v3 论坛动力学的核心新输入 |
| `card.source_cards` | card 间关联,带 `relation`;承担 v2 `link create` 的部分语义,但**创建时确定不可改** |
| `card.stats` | 6 个计数器(`review_up` / `review_down` / `review_neutral` / `review_count` / `read_count` / `recall_count`),沉浮公式的输入信号 |
| `search.ranking_formula` | 单一可配置公式替代多档 sort 模式(no `--sort hot/new/top`),公式在 settings 里改 |

### 改名 / 收编

| v2 | v3 |
|---|---|
| `view` | `read`(语义没变,改名更口语) |
| `card.summary` | `card.insight`(强调"洞见"而非"摘要") |
| `card create` | `card`(取消 `create` 子命令) |

### 显式去掉

| v2 命令 / 概念 | v3 为什么不要 |
|---|---|
| `filter` | 论坛动力学(沉浮公式 + DSL)替代了"取景框",找特定子集走 `search --where`,不再写独立 filter 引擎 |
| `tag` | 没有 tag 命令,session 也不再带 `tags` 字段 —— 元数据筛选靠 `source` / `created_at` 等已有字段足够,自动 tag 机制(`sync_session` / `explore`)随 filter 一起退场 |
| `link create` / `link list` | 用户 link 压成 card 的 `source_cards`(immutable);card↔session 仍由 `rounds[].session_id` 隐式承载,不再有独立 link 对象 |
| `log` | events.jsonl / search_log 仍作为后端审计层存在,**但不开 CLI 查询入口** |
| `rebuild` | embedding 重算捆在 `setup`(仅 dim 改时触发,就地重算所有 card 向量),不开独立 rebuild 命令 |
| TTL 整套 | `card.initial / factor / max`、`link.*` 全去掉。沉浮不靠 TTL 衰减,靠 review 分布 + age_days 在公式里直接算 |
| `explore` | 整套抽 card 工作流**待重新设计** —— v2 explore 强依赖 filter + tag,这两个去掉之后整个 pipeline 要重画 |

## 五、典型工作流

### 第一次跑

```bash
memory-talk setup                # wizard:embedding / vector / relation provider + port
memory-talk server start         # 起后台 API
memory-talk sync start           # 启动后端 watcher;此后 Claude Code 会话实时落库,日常不用管
```

### 日常读写(LLM 通过 tool-use 调)

```bash
# 1. 在某次会话里沉淀一张 card
memory-talk card '{
  "insight": "选定 LanceDB 做向量存储",
  "rounds": [{"session_id": "sess_abc", "indexes": "11-15"}]
}'

# 2. 几周后翻到这张 card,觉得仍然成立 / 错了 / 部分对
memory-talk review '{
  "card_id": "card_01jz8k2m",
  "session_id": "sess_def",
  "indexes": "20-25",
  "score": 1,
  "comment": "三个月生产稳定运行,选型正确"
}'

# 3. AI 主动检索 / hook 阶段无意识召回
memory-talk search "LanceDB 选型"
memory-talk recall sess_def "用户当前的 prompt"

# 4. 读单张 card,看完整内容 + 论坛位置(Stats / From / reviews / rounds)
memory-talk read card_01jz8k2m
```

### 翻 shadow knowledge

```bash
# 被读 / 召回很多但没人真讨论过的 card
memory-talk search "" -w 'read_count + recall_count > 10 AND review_count = 0'

# 被反驳多于支持的 card(动力学上可能要 fork)
memory-talk search "" -w 'review_down > review_up'

# 高争议:赞踩都不少
memory-talk search "" -w 'review_up >= 3 AND review_down >= 3'
```

### Fork 一张 card

Fork 不是一条命令,是**新建一张 card,在 source_cards 里指回老 card**:

```bash
memory-talk card '{
  "insight": "改用 Postgres + pgvector,LanceDB NFS 部署不稳",
  "rounds": [{"session_id": "sess_ghi", "indexes": "3-8"}],
  "source_cards": [
    {"card_id": "card_01jz8k2m", "relation": "supersedes"}
  ]
}'
```

老 card 不删不改;新老两边都继续接收 review,谁最终活下来由沉浮排序说了算。

### 改 embedding 配置

```bash
memory-talk setup                # 改 provider / dim,setup 就地重算所有 card 的 embedding(阻塞,进度 stderr)
```

## 六、命令详情

| 命令 | 文档 |
|---|---|
| `setup` | [setup.md](setup.md) |
| `sync` | [sync.md](sync.md) |
| `card` | [card.md](card.md) |
| `review` | [review.md](review.md) |
| `read` | [read.md](read.md) |
| `search` | [search.md](search.md) |
| `recall` | [recall.md](recall.md) |
| `server` | 沿用 v2 [server.md](../v2/server.md) 契约,后续补独立 v3 版 |

## 七、设计原则

四条不变性,前两条沿用 v2,后两条 v3 新立:

1. **Python 不调 LLM API**:所有认知工作走 Skill / agent;CLI 只做机械数据操作(从 v2 沿用,见 [`CLAUDE.md`](../../../CLAUDE.md))。
2. **CLI 命令 = 一次机械操作**:一个命令一件事,JSON 输出,人 / agent 都好处理。
3. **Card append-only**:`insight` / `rounds` / `source_cards` 创建即冻结。评价 / 引用 / 反驳走 `review` 或新开 card,不改老 card。
4. **状态从动力学算,不存字段**:card 没有 `state` 字段;dormant / superseded / hot 都从 stats + age 实时算。不做状态机迁移,避免"动力学"和"状态机"两套真相打架。

第 3 / 第 4 条联合保证一个性质:**lineage 自然成 DAG**(card 创建后不可改 + `source_cards` 只能指向已存在的 card → 物理时序排除循环)。系统不做环检测。

---

工程边界 / 数据物理布局(sessions/ / cards/ / vectors/ / logs/)沿用 v2 的目录形态;v3 暂不重写 `structure/` 下的文档,有需要时直接看 backend 代码或 sqlite schema。
