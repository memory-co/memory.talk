# works / columns — 列(弱编排)+ 工作单元在哪一列第几个;一个动作一个请求,动了哪一列进轨迹

## 这个场景在测什么
一列 = 固定编号 + 别名(`docs/designs/v5/work-events.md`),库里是 `work_columns` 的行、工作单元摆在哪是 `worklets` 的列(`docs/designs/v5/work-store.md §4`);
没有别的布局对象:`GET /columns` 是列清单(从左到右,带 `position`),`GET /worklets` 的每个工作单元带 `column` / `position` / `collapsed`;`/canvas` 已撤(404)。
新 work 就有一列 `c1`(position 0);加列由服务端发 `c<n>`,单调递增、删了也不复用;加在 `beside` 的左边(占它的位置)或右边,不给 = 最右;列的 position 始终连续;
列 id 只认 `c<编号>`,别的写法 404(编号大过 sqlite 整数、位数多到 `int()` 解不了的也是 404,改 / 删 / beside / 挪 / 打开都一样,而且什么都不动);
列上的动作(加 / 改 / 删)交回列清单;改别名编号不动,打一个 `column.renamed` 点(带 `memorytalk.from`);加 / 删列打 `column.added` / `column.removed` 点;收起 / 展开(列和工作单元)不进轨迹;
最后一列不能删、里面还有工作单元的列不能删(409),不存在的列 → 404;
打开时先验过列在、现场还在建的那一会儿列被删了 → 404 `not_found`(不是 409),刚建的现场销毁掉,不登记、不开段(撞车用 monkeypatch 卡在 `work_servers.open` 里直接调服务方法来造)。
工作单元开的时候定列(给了放那列末尾,不给 = 最左一列,即 position 0 那列),交回的工作单元就带在哪一列第几个,开一个 `worklet` 段(挂在 work 段下,带列和 `user.id`);重入交回的也带;
挪动 / 收起交回工作单元清单(按开的先后);挪动打 `worklet.moved` 点(去哪 / 从哪的列和位置,位置按「先从原列拿掉」之后数,超出放末尾,不给 = 末尾);同一列里 position 始终连续,关掉一个后面的往上补;
关掉工作单元列还在,`worklet` 段结束(`memorytalk.end.reason = detached`,带关的时候在哪一列);工作单元 id 也不复用(关了 `-w1` 下一个是 `-w2`)。
轨迹用 `tests/_util.py` 的 `trace()` 拍平了看。

## 不在这测什么
- 工作单元的建立本身 → `work_servers/`
- 轨迹的 id、OTLP 形状 → `works/trace`

## fixture 来源
`client` / `svc` / `H`;网页工作单元(`https://`)不起 tmux,开真 tmux 工作单元的几条标了 `needs_tmux`。
