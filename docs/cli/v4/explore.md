# explore

**v4 的「抽 v4 卡工作台」是下一轮设计、尚未实施。** 本页只说明现状与意图。

## 现状(沿用 v3 机制)

抽卡当前仍走 v3 的 explore 工作台:在 explore 目录里**逐 round 走 [`session mark`](session.md#session-mark) 打注解**,mark 里 `#…？` 就地标问题、写入时自动建卡 / 关联老卡。相对 v3 唯一的产物差异:

| | v3 explore 产物 | v4 explore 产物 |
|---|---|---|
| 抽出来的是 | 一张 insight 卡(一句陈述 + rounds + stats) | 一张 **v4 卡**(一个问题 Issue + 若干答案 Position) |
| 写入路径 | v3 探洞见 | [`session mark`](session.md#session-mark)(逐 round 注解,`#…？` 自动建 v4 卡) |

现状的工作台命令(`explore pending` / `list` / `detail` / `auto` / `manual` 等)行为**沿用 v3**,见 [`../v3/explore.md`](../v3/explore.md)。

## 下一轮设计(未实施)

v4 专属的 explore 子命令(把「抽 v4 卡」从 v3 工作台里独立出来、围绕问题图 + Position 竞争重排工作流)留待下一轮设计;设计推理见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。

> **状态**:v4 explore 工作台为**设计提案、未实施**;现状抽卡走 [`session mark`](session.md#session-mark) + [`../v3/explore.md`](../v3/explore.md)。
