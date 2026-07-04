# card — mind 写动作(v5 CLI)

mind 库唯一写门的命令壳(调 [写动作端点](../../api/v5/cards.md));读一律走 [`query`](query.md)。**证据参数统一 `--proof <type>:<ref>:<indexes>`**(`(type, ref)` 模式;当前 type 只有 `session`,如 `--proof session:sess_abc:11-15`),可多次。文本参数支持 `@<file>` / `@-`(沿 v4)。

## card create — 建卡(撞库判新内建)

```bash
memory.talk card create --issue '为什么 pty 会让用户想到 tmux？' \
    [--proof session:sess_def456:36-37 ...] [--json]
```

服务端 embed 撞库:**miss 建新卡 / hit 返回既有卡**(输出标 `is_new`)——判新交给检索,调用方不用自己想「这问题新不新」。

## card position — 加答案

```bash
memory.talk card position --card card_01j… --claim '他要的是可重连会话' \
    --proof session:sess_def456:36-41 [--scope '<场景>'] [--json]
```

`--proof` 必填(答案必须有出处)→ 输出 `card_01j…#p1`(序号服务端 mint)。

## card review — 表态

```bash
memory.talk card review --target card_01j…#p1 --argument +1 \
    --proof session:sess_abc:20-25 [--comment '再次确认接住了'] [--json]
```

`--target` 分片定对象(`#p<n>` 答案 / `#l<n>` 边);单条 `--proof`(一次表态一份证据);credence 不落库,`query` 时视图现算。

## card link — 连边

```bash
memory.talk card link --card card_01j… --type specializes --target card_09a… \
    --claim '两卡同一套 auth,这张是特化' [--proof session:sess_abc:30-34 ...] [--json]
```

幂等:重复连边返回既有 `l<n>`。

## card delete — 墓碑级联

```bash
memory.talk card delete card_01j… [--yes] [--json]
```

默认先 dry-run 预览计数(答案 / 表态 / 出入边 / proofs / 向量)→ `继续删除? [y/N]`;`--yes` 跳过;`--json` 须配 `--yes`。**删 = 全部打墓碑**(无物理删;`query --as-of` 仍能回放它生前的样子)。

## 改主意的姿势(不变的 IBIS 纪律)

答案错了**不删不改**:`card position` 加新答案 + `card review --argument -1` 踩旧的,credence 现算会把新答案抬上来;边错了同理(踩它或加 `replaces` 反向边)。`merge` / `decay` 已列入动作集、本版不定形(见 [api/cards.md](../../api/v5/cards.md))。
