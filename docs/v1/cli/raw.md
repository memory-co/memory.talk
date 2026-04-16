# raw

访问原始对话数据。

## raw read

读取 session 的原始 rounds，可指定范围。

```bash
memory-talk raw read <SESSION_ID> [START] [END]
```

- 不指定 START/END：返回全部 rounds
- 指定 START END：返回 `[START, END)` 范围内的 rounds
