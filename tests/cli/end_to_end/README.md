# cli / end_to_end — 命令行走一遍

## 这个场景在测什么
真起一个服务(随机端口、临时 home、独立 tmux socket),用 `python -m memorytalk` 跑 docs/cli/v5 的主线:
`server start / status / stop`(幂等、状态验证)、`user add / list / whoami`(没注册的名字当身份 → exit 1)、
`work create / list / set / attach / sessions / detach / show / servers`、`collection write / act / edit(@-) / read / log / search / tree / manager / managed / layers`、
`work inbox`;`--field` 的 JSON / 逗号列表 / `a.b` 嵌套;`--json` 输出的是信封里的 `data`。

## 不在这测什么
- 每个 API 的语义 → 各层场景

## fixture 来源
本目录自建 `cli` fixture(subprocess + 真服务);需要 tmux。
