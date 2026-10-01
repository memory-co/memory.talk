# work_servers / freeze — work 结束,现场销毁、登记留着

## 这个场景在测什么
work 归档(`archived`)之后:所有工作单元的 tmux 现场被销毁,`worklets` 清单里还在但 `alive: false`,画布上的位置也还在;
重入(`POST …/worklets/{id}/attach`)409,现场不再起来,也不开段;
轨迹里 work 段和开着的 worklet 段一起结束(`memorytalk.end.reason = archived`),不另记「冻结」,之后列清单也不会再记成 `gone`。

和别的请求撞在一起的时候:
- 现场正在建,work 被归档了 → 打开 409,刚建的现场销毁掉,不登记、不上画布、不开段;
- 归档 / 关掉销毁了现场、还没结束段的那一会儿有人列清单 → 不记成 `gone`,段照样是 `archived` / `detached`,记的是归档 / 关掉的人;
- 列清单看到现场没了、紧接着有人重连把它开起来了 → 不记成 `gone`,段接着开着。
撞车用 monkeypatch 卡在 `work_servers.open` / `destroy` / `alive` 里面直接调服务方法来造。

## fixture 来源
`client`、`svc`、`H`、真 tmux(`needs_tmux`)。
