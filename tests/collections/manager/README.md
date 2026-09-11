# collections / manager — manager.json:目录绑 work,最近祖先优先

## 这个场景在测什么
`manager.json` 放在任何目录(含对象自己的目录);解析往上找最近的一个;对象目录里的比主题文件夹的近;解绑回到上一级;
`managed?work=` 列这个 work 管的对象,不带 = 没人管的;manager.json 在 `.issue/` 里随 `[issue]` 提交,在普通目录里归最底层。

## 不在这测什么
- 变动投递到收件箱 → `inbox_delivery`

## fixture 来源
`client`、`_util.git_log`。
