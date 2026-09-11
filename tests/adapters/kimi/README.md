# adapters / kimi — 读 Kimi Code 的 wire 记录

## 这个场景在测什么
`KimiAdapter`:`~/.kimi-code/sessions/wd_*/session_*/state.json` 的 `workDir` 匹配工作目录,记录在 `agents/main/wire.jsonl`;
`turn.prompt` → human,loop event 里 `content.part`(text / think)→ assistant,`tool.call` / `tool.result` → 工具调用与结果。

## fixture 来源
`home`(临时的 kimi 记录根)。
