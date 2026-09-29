# works / canvas — 列 × 工作单元;一个动作一个请求,动了哪一列进事件

## 这个场景在测什么
一列 = 固定编号 + 别名(`docs/designs/v5/work-events.md`):新 work 的画布就有一列 `c1`;加列由服务端发 `c<n>`,单调递增、删了也不复用;
改别名编号不动,记 `column.renamed`(带 `from`);加 / 删列记 `column.added` / `column.removed`;收起 / 展开(列和工作单元)不记事件;
最后一列不能删(409),不存在的列 → 404;`PUT /canvas` 已撤(405);旧画布读的时候规整(`name` 读作 `alias`,非 `c<n>` 的 id 接着发号)。
工作单元开的时候定列(不给 = 最左一列),`worklet.attached` / `worklet.moved` / `worklet.detached` 都带列标记 `{id, alias}` 和 `by`;
关掉工作单元列还在;工作单元 id 也不复用(关了 `-w1` 下一个是 `-w2`)。

## 不在这测什么
- 工作单元的建立本身 → `work_servers/`

## fixture 来源
`client` / `svc` / `H`;开真工作单元的几条标了 `needs_tmux`。
