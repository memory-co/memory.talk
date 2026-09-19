# auth / gate — 先立 admin,再进门

## 这个场景在测什么
没有 `admin` 时除了 status / setup 全部 409 `setup_required`;setup 只能做一次,做完就登录了;
登录:密码换 token,错的 401;logout 作废 token;改密码要旧密码(admin 给别人设不用),改完这个人的 token 全作废;
只有 admin 能建账号、改别人的档案;密码哈希不从任何接口出去。

## 不在这测什么
- token 怎么变成 work / commit 上的名字 → `users/identity`
- CLI 的 setup / login / logout → `cli/end_to_end`

## fixture 来源
`home`(自己起 app,因为要看没 setup 的状态)、`client`、`H`。
