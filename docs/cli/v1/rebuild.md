# rebuild

从文件系统重建 SQLite 索引和 LanceDB 向量库。异步执行。

```bash
memory-talk rebuild
```

删除 SQLite 和 LanceDB，从 sessions/ 和 cards/ 目录扫描重建。TTL 重置为默认 initial 值。

输出：
```json
{"status": "rebuilding"}
```
