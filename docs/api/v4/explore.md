# Explore API

**v4 的 explore 端点是下一轮设计、尚未实施。**

## 现状(沿用 v3)

抽 v4 卡当前不走独立的 v4 explore 端点;现状沿用 v3 的 explore 工作台接口,见 [`../v3/explore.md`](../v3/explore.md)。v4 抽卡的实际写路径是逐 round 注解 —— 见 [`session-marks.md`](session-marks.md)(`POST /v4/sessions/{id}/marks`),其产物从 insight 卡换成 v4 卡(问题 + 答案)。

## 下一轮设计(未实施)

围绕 v4 问题图 + Position 竞争重排的专属 explore 端点留待下一轮设计;设计推理见 [`../../works/v4/session-mark.md`](../../works/v4/session-mark.md)。

> **状态**:v4 explore 端点为**设计提案、未实施**;现状走 [`session-marks.md`](session-marks.md) + [`../v3/explore.md`](../v3/explore.md)。
