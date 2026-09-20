# work_servers / registry — server 自己声明协议,没人声明的去 default

## 这个场景在测什么
`GET /api/works/servers` 列出六个 work server 及各自的 `protocols`;`default` 不声明、排最后;
寻址在服务层:协议在谁的 protocols 里就是谁(`https` → http),没人声明 → default。没有单独的 resolve 端点。

## 不在这测什么
- 建现场 → `bash_worklet` / `http_worklet` / `default_worklet`

## fixture 来源
`client`、`svc`。
