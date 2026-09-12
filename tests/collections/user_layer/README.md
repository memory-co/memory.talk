# collections / user_layer — 往 `<home>/layers/` 放一个 .py 就是一层

## 这个场景在测什么
用户层和内置层一模一样:`<home>/layers/<name>.py` 里写一个 `Layer` 子类,启动时载入,排在内置层之上(`builtin: false`),
`collections.json` 里自动补一项、新分支从始祖出发;它的 `check` 说了算(这里的例子:清单外文件拒、`readme.md` 必需、`runs/*.md` 只能追加、`result.yaml` 必须有 `verdict`),
拒的理由原样带回;文件里没有 Layer 子类 → 启动失败;文件删了但 `collections.json` 里还有 → 启动失败。

## fixture 来源
`home`(拿到 `MEMORY_TALK_HOME`,写 .py 后自己 `create_app`)、`_util.git_log`。
