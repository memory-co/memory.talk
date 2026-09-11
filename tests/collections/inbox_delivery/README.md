# collections / inbox_delivery — 变动打到 manager work 的收件箱

## 这个场景在测什么
一个主题文件夹绑了 work 之后,它下面**不分层**的每次提交都进那个 work 的收件箱(记层、路径、动作、谁、从哪个 manager.json 路由来);
带 `X-Memory-Talk-Work` 的自己造成的变动不投给自己;`manager.json` 自己的变动不投递;没人管的变动进 `unmanaged`。

## fixture 来源
`client`、`H`、`svc`。
