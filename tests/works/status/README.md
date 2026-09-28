# works / status — 两档:运行中 / 归档

## 这个场景在测什么
新 work 是 `running`;改成 `archived` 写 `archived_at`,拿回 `running` 清空;父 work 归档不看子 work(各归各的);
写入只认两档(旧的 `done` 等 → 422),但磁盘上旧的四档读进来会折成两档(`todo` / `doing` → running,`done` / `abandoned` → archived,`done_at` 读作 `archived_at`);
归档的 work 不能再 attach 工作单元(409)。

## 不在这测什么
- 归档时现场销毁 → `work_servers/freeze`

## fixture 来源
`client`。
