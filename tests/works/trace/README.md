# works / trace — work 的经过:段 + 点,OTLP/JSON

## 这个场景在测什么
轨迹存在 `worktrace.db`(`docs/designs/v5/work-trace.md`、`work-store.md §5`),`GET /works/{id}/trace` 拼成 OTLP/JSON 的
`{"traces": TracesData, "logs": LogsData}`;旧的 `/events` 撤了(404)。
- 建 work 开一个 `work` 段(开着:没有 `endTimeUnixNano`,带 `memorytalk.open = true`);归档结束它,开着的 `worklet` 段一起结束(`memorytalk.end.reason = archived`,
  `memorytalk.end.user.id` 是归档的人);重新打开是同一个 work 的新一段,`links` 指向上一段;
- id 由身份算出来:trace id = 根 work,work / worklet 段 = 「谁 + 第几段」;子 work 的段挂在父 work 的段下,worklet 段挂在 work 段下;
- 改目标打 `work.renamed` 点;关掉工作单元结束它的段(`detached`,谁关的);现场自己没了,列清单时把段结束成 `gone`(status Unset),重入再开新的一段;
- 归档后重新打开,现场还活着的工作单元(网页的)接着开新的一段(挂在新的 work 段下),之后挪它、关它都记在这一段上;
- 关掉时已经没有开着的段(归档过又重新打开没重连、现场没了 `gone`),段不再动,打一个 `worklet.closed` 点(谁、在哪一列),关的人也算动过这个 work;
- `subtree=true` 带上所有子孙;
- 同一个 work 的生命周期动作排队:归档还在收尾(销毁现场)时有人重新打开,等归档做完再开新的一段,归档结束的是它自己那段;
  登记写进去、段还没开时有人归档,等段开好了一起结束;一个 work 同时只有一段 work 段开着——归档结束所有开着的 work 段,
  上一次归档的轨迹没写进去的,重新打开时先按归档补上终点(不记人);
- 已归档的 work 不能重入(409):直接点的、归档半中间点了重连等着的,都不在结束了的 work 段下开出 worklet 段;重新打开之后又能重入;
- 归档读「工作单元此刻在哪一列」是一个事务里的两次读:中间别人把它挪走、删了空出来的列,得等读完——归档不报错,段照样结束,带的是归档那一刻的列;
- 轨迹写失败不让动作失败(works.db 照常提交)。

## 不在这测什么
- 画布动作各打什么点 → `works/canvas`
- agent 的轮次(`agent.turn`)和 round → `adapters/claude_code`、`adapters/turns`

## fixture 来源
`client` / `svc` / `H`;网页工作单元(`https://`)不起 tmux,现场没了 / 归档销毁现场的几条标了 `needs_tmux`。轨迹用 `tests/_util.py` 的 `trace()` 拍平了看。
