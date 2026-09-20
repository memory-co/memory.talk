# settings —— 设置页

`Settings.tsx`:

- **账号卡**:头像、显示名、角色徽章、退出登录;`ProfileForm`(改自己的显示名 / 邮箱,`PUT /users/{me}`)、`PasswordForm`(self 模式:旧密码 + 新密码,改完清登录态回登录页)。
- **团队成员**:所有能登录的人;admin 多「添加成员」(`RegisterUser`:用户名 / 显示名 / 邮箱 / 初始密码,`POST /users`)和每行的「设置密码」(`PasswordForm` 非 self 模式,`PUT /users/{name}/password` 不用旧密码)。
- **语言**:zh / en,存浏览器。
- **环境**:`GET /system/info` 的路径、存储、终端窗口(tmuxd 的 host:port)、tmux socket。
