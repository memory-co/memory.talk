# adapters / turns — round 切成 agent 轮次

## 这个场景在测什么
`services/work/turns.py` 的两个纯函数(`docs/designs/v5/work-trace.md §2、§10`),不起服务:
- `round_time_ns`:各 adapter 的时刻统一成 Unix 纳秒——Claude Code / Codex 的 ISO 串(`Z` 或带时区,小数秒到纳秒,没写时区当 UTC)、
  Kimi 的 Unix 秒(数字或数字串);解不出来 → `None`;
- `slice_turns`:一轮 = 人的一条输入(`human`)起、到下一条人的输入之前;第一条人的输入之前的不算;后面有人的输入就结束了
  (终点 = 这一轮最后一条 round 的时刻),最后一轮开着;没时刻的沿用前面最近一条;一轮里一个时刻都没有就不出;终点不早于起点;
- 用 Kimi / Codex adapter 真读出来的 round 切一遍。

## 不在这测什么
- 轮次写进轨迹(`agent.turn` 段的 id、父、幂等、关掉时收尾)→ `claude_code`

## fixture 来源
纯函数直接调;读真实记录的两条用 `home`(临时的 kimi / codex 记录根)。
