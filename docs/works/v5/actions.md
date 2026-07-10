# actions — 受治理写动作:语义、merge / decay 定形、权属分级(v5 设计)

> **状态:设计中。** 能力层的**写侧**:mind 库唯一的写门是这组动作([mind-data §5](mind-data.md)),每个动作 = seekbase 的一次 insert / delete(ticket)编排 + 动作层校验。本篇定**动作本身的语义与不变性**——「棋子的走法」;**怎么用动作(结晶 / 治理 / 巩固的流程)不预制**,那是 agent 的策略([agent](agent.md) 的自进化空间)。wire 契约见 [api/v5/cards.md](../../api/v5/cards.md)。

相关:
- 动作的宿主(每 agent 写自己的 mind): [agent.md](agent.md) · 表与视图: [mind-data.md](mind-data.md)
- 引擎(ticket / insert-only / 时光机,动作的不变性靠它兜底): [seekbase.md](seekbase.md)

---

## 1. 动作清单与共同不变性

| 动作 | 效果 | 幂等性 | 权属级(§4) |
|---|---|---|---|
| `create_card` | 撞库判新:miss 建卡 / hit 返既有(`is_new`) | 撞库天然幂等 | A(自主) |
| `add_position` | 加答案(`p<n>` mint = max+1;proofs 必填) | 否(重复 = 新答案,append 语义) | A |
| `review` | 表态 ±1/0(单条引证) | 否(同一目标可多次表态,不去重) | A |
| `link` | 连边(UNIQUE (card_id, type, target_id)) | 是(重复返既有 `l<n>`) | A |
| `decay` | 衰减:append 一条衰减事件(§3) | 否(可叠加) | A |
| `merge` | 合并两卡:边 + proofs 并入 + 墓碑(§2) | 是(重复 merge 无效果) | **B(在环)** |
| `delete` | 墓碑级联(dry-run 先行) | 是 | **B(在环)** |

**共同不变性**(全部由动作层 + seekbase 兜底):
- 一切动作 = **append**(insert)或**墓碑**(delete);没有任何就地修改;
- **证据强制**:position / review / link 必带 `(type, ref, indexes)`(create_card 的 proofs 可选但强烈建议);
- **判断类校验不外包给调用方**:新不新(撞库)、边重不重(UNIQUE)、序号 mint——全在动作里;
- 每个动作一个 ticket(或一串按序 ticket),`wait` 后读己之写;时光机可回放任何动作前后。

## 2. merge 定形:动作只做机械部分,判断留给 agent

`merge(survivor, absorbed, claim)` 的语义,**三步、全部机械**:

1. **连边**:survivor 加一条 `replaces` 边指向 absorbed,`claim` 必填(为什么是同一个问题)——这条边就是合并的「判决书」,受治理(可被 review 反对);
2. **证据并入**:absorbed 的 `card_proofs` 逐条 append 到 survivor(同 `(type, ref)` 合并 indexes)——**证据不丢**;
3. **墓碑**:absorbed 及其 positions / links 级联打墓碑(时光机随时可回放合并前)。

**答案(positions)不自动搬**——这是有意的:absorbed 的答案是「对旧问题措辞」的答案,适不适用于 survivor 是**判断**,不是搬运。要留的答案,agent 在 merge **前**自己 `add_position(survivor, claim=…, forked_from="absorbed#p<n>")` 挂过去(forked_from 留血缘)。**动作不替 agent 做判断**,一如 create_card 不让 AI 自评新旧。

幂等:重复对同一对执行 = 边已存在(UNIQUE)、proofs 已并、absorbed 已墓碑 → 无效果。

## 3. decay 定形:一张事件表,口径在视图

衰减的诉求:老信念没有新证据支撑时,credence 该随时间「降温」——但 **up/down 是表态、不该被伪造**(用假 review 实现衰减会污染表态史)。定形:

- **新事件表 `decay_events`**(mind 库):`(card_id, target, amount, reason, created_at)`——append-only,`target` = `'p<n>'` / `'l<n>'`,`amount` 默认 1,`reason` 必填(如「180 天无新证据」);
- **credence 口径在视图收编**:`v_positions.credence = up − down − Σ decay`——衰减参与排序但**不碰 reviews**(表态史干净;时光机下衰减史也可回放);
- 谁触发:agent 拿 [metrics](metrics.md) 的「最优答案陈旧度」队列,逐个 decay(reason 写明依据)——**衰减是动作,判断何时衰减是策略**;
- 反悔:不删事件(insert-only),用一条负 amount 的 decay 事件冲销,或加新 review 抬回来。

## 4. 权属分级:只增的自主,收窄的在环

「哪些动作可以无人监督地做」——判据一句话:**会不会缩小当前可见的信息面**。

| 级 | 动作 | 理由 |
|---|---|---|
| **A · 自主** | create_card / add_position / review / link / decay | 全是 append:错了可反制(踩回来、冲销),不丢任何信息;最坏结果是噪声,而噪声有治理队列兜着 |
| **B · 在环** | merge / delete | 打墓碑 = **当前态收窄**(时光机能回放 ≠ 当前可见);初期 human-in-loop——agent 在 chat 里请示(「4 张卡拟合并成 2,可以吗?」),人批了才执行 |

- B 级的「在环」是**阶段性的**:等 [metrics](metrics.md) 的护栏组跑稳、agent 的 merge 判断有了对照记录,可以按实例放权(per-agent 配置),放权后靠**事后审计**(chat 的 `actions[]` + 时光机回放)兜底;
- quickjs harness 的**自进化改自己**(engine_versions)天然是 B 级(影子对照 + 切换拍板,[agent §3](agent.md))——同一个判据:切换引擎版本改变的是「谁在管这个 mind」,比墓碑更收窄。

## 5. 待定

- **merge 的辅助**:要不要给「候选答案预览」(merge 前列出 absorbed 的 positions + credence,提示 agent 逐个决定)——工具性辅助,不是自动搬;
- **decay 公式**:线性扣减(当前)vs 半衰期;`amount` 的量纲要不要跟 review 的 ±1 对齐;
- **批量动作**:治理轮常常一批 review / decay——要不要批量端点(ticket 数组),还是逐个调(seekbase 批量 insert 已支持,先逐个);
- **B 级放权的门槛**:多少次「人批 = agent 拟」的一致率才自动化。

## 与其他 v5 文档的关系

- [mind-data.md](mind-data.md):§5 写动作面的展开;`decay_events` 是本篇新增的表(credence 视图口径随之演进——好在只改视图);
- [api/v5/cards.md](../../api/v5/cards.md):wire 契约(merge / decay 从「保留不定形」升级为本篇语义);
- [agent.md](agent.md) / [metrics.md](metrics.md):动作的使用者与触发依据;B 级在环走 chat。
