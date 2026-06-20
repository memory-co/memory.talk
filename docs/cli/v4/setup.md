# setup

**v4 与 v3 一致** —— `memory.talk setup` 是交互式幂等安装向导:首次安装 / 改配置 / 重启 server / embedding 重算,行为、参数、wizard 流程**完全照 v3**,本目录不复制。

```bash
memory.talk setup
```

**v4 唯一变化**:无。`setup` 是纯沿用的基础设施,连本地端点前缀都不涉及(setup 直接读写 `settings.json` + 起停 server,不是 `/v3`→`/v4` 那类 HTTP 命令)。

> 完整契约(wizard 各步、幂等语义、改配置 / 重启 / embedding 重算的细节)见 [`../v3/setup.md`](../v3/setup.md)。配置文件结构见 [`../../structure/v4/settings.md`](../../structure/v4/settings.md)(v4 向量 collections 有增量,余沿用 v3)。
