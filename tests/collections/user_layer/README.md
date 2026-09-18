# collections / user_layer — 往 `<home>/layers/` 放一份 YAML 就是一层

## 这个场景在测什么
用户层和内置层是同一种东西:`<home>/layers/<name>.yaml` 一份协议,启动时载入,排在内置层之上(`builtin: false`),`collections.json` 里自动补一项、新分支从始祖出发;
`GET /layers` 原样给出它的协议;引擎按它校验(清单外文件拒、required、字段类型、date);协议写错(未知类型、正则不合法、pattern 不以 .<层> 结尾、两种文件重叠)→ 启动即报错;
文件删了但 `collections.json` 里还有 → 启动报错。

## fixture 来源
`home`(拿到 `MEMORY_TALK_HOME`,写 .yaml 后自己 `create_app`)、`_util.git_log`。
