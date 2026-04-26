# test_settings

`Config.settings` —— Pydantic settings 对象 (server / search / embedding 等),
默认值 + `settings.json` 覆盖路径。

## 场景矩阵

| 测试函数 | 验证什么 |
|---|---|
| `test_settings_defaults` | 不存在 settings.json 时,`server.port=7788`,`search.default_top_k=10`,`embedding.provider="dummy"` 等默认值就位 |
| `test_settings_loaded_from_json` | 写入 settings.json 后,字段被覆盖,未提到的字段保留默认 |

## 覆盖的代码路径

- `config.py::Config.settings` 的 lazy load(读 `settings.json`,Pydantic 解析)
- 默认值合并:文件里没写的字段不会被冲掉

## 为什么默认 embedding=dummy

测试套和"刚拉下来跑"的开发场景不应该强依赖网络/key。dummy embedder 是
"拿到向量但不真嵌入"的占位,server 能起来,搜索能跑(质量当然差)。
