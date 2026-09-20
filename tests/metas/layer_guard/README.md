# metas / layer_guard — 一个提交只属于一层,碰了别的层被拒

## 这个场景在测什么
写入时的守卫(服务层直接试):声明 `[card]` 却碰 `.issue/` 里的文件 → 拒(`guard`);同层编辑通过;
每条 `layer/<层>` 分支上只有自己层的提交,`stack` 的 first-parent 是全部认知的时间线。

## fixture 来源
`client`、`svc`、`_util.git_log`。
