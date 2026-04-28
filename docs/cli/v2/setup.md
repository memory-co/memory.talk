# setup

**纯交互式**的幂等安装 / 配置 / 重启。第一次跑是 wizard,引导用户初始化 data root + settings.json + 启动服务;后续再跑就是"修改配置 + 必要时重启服务"。同一个命令覆盖两个场景,用户不需要记两套姿势。

**没有 `--json` 模式**。setup 的设计目的就是逐项交互、让用户确认每个字段在干嘛 —— 把它"自动化"反而违背初衷。CI / 自动化场景请直接写 `settings.json` + 调 `server start`,不走 setup。

```bash
memory-talk setup [--data-root PATH]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--data-root` | `~/.memory-talk` | 数据根目录。指定路径后所有 prompt 都基于这个根。 |

**`setup` 不支持 `--json`** —— 它的核心价值就是逐项交互式确认,把"理解每个字段在干嘛"这一步硬塞给用户。脚本化场景请直接写 `settings.json` + 调 `server start`,不要走 setup。

## 行为分支

setup 进来先看 `<data_root>/settings.json` 是否存在,据此分两种走法。

### 首次安装(没有现有 settings.json)

走完整 wizard:

1. 创建 data root 目录(若不存在)
2. **安装模式**(detect → 必要时询问):
   - **标准模式(推荐)**:在 `<data_root>/.venv/` 下创建独立 venv,把 `memory-talk` 装到里面,跟系统 / 全局 Python 完全隔离。后续所有命令通过软链(下面第 10 步)走这个 venv,不会被系统级 `pip` 或别人改的 Python 包污染。
   - **使用当前**:沿用当前 `memory-talk` 所在 Python 环境(可能是系统 Python、`pip --user`、用户自己的 venv……)。适合"我自己管 Python 环境"的开发者。
   
   **检测规则**:`shutil.which("memory-talk")` 拿到的脚本路径如果是 `<data_root>/.venv/bin/memory-talk`,**已经在标准模式,不询问**,跳过此步。否则提示:
   
   ```
   检测到当前 memory-talk 在: /usr/local/bin/memory-talk
   推荐切换到标准模式(在 <data_root>/.venv 装独立 memory-talk),避免环境耦合。
   选择: [1] 标准模式 (推荐)  [2] 使用当前
   ```
   
   选 [1] 后 setup 会:
   - `python3 -m venv <data_root>/.venv` 建 venv
   - `<data_root>/.venv/bin/pip install memory-talk` 安装
   - 后面第 11 步的软链**指向** `<data_root>/.venv/bin/memory-talk`,而不是当前 PATH 上的那个
   
   > **TODO(未实现)**:pip 包 `memory-talk` 还没发布到 PyPI。当前 setup 跑到这一步遇到"标准模式"会**报错并指向手动安装文档**。等 PyPI 上线后这一段自动跑通。文档先把契约定下来,实现一并补。

3. 选 **embedding provider**(只有两档,因为 setup 只面向真实使用场景):
   - `local` — sentence-transformers,本地 CPU/GPU 跑模型
   - `openai` — OpenAI 兼容 HTTP 端点(OpenAI / DashScope / vLLM 等)
4. 根据选择填细节:
   - `openai` → endpoint / `auth_env_key` / `model` / `dim`,**实时打 HTTP 探针**验证 endpoint + key + dim
   - `local` → 模型名(默认 `all-MiniLM-L6-v2`),首次会触发模型下载
   
   > `dummy` provider 仍然存在于代码里,**只服务测试**,setup 不暴露 —— 不应该让真实用户在生产 / 个人配置里选到一个"假 embedding"。手工编辑 `settings.json` 写 `provider=dummy` 仍然可以,但不是 setup 的产物。
5. 选 **vector provider**(向量数据库):
   - `lancedb` —— 嵌入式,零运维,自带 FTS。**当前唯一选项**,wizard 仍把它显式 prompt 出来,便于后续扩展(比如加 Pinecone / pgvector)时用户脑子里有"这一步是个选择"的认知。
6. 选 **relation provider**(关系数据库):
   - `sqlite` —— 嵌入式,零运维。**当前唯一选项**,同样显式 prompt。
7. 选 **server port**(默认 `7788`)
8. 写 `settings.json`(原子写:tmp + rename)
9. `ensure_dirs()` 把 `sessions/ cards/ links/ vectors/ logs/search/` 全部创建出来
10. 询问"现在启动 server 吗?",`yes` 则等价于跑一次 `server start`,`no` 则给用户**复制粘贴的下一步命令**
11. **创建 `memory.talk` 软链**:setup 最后一步,在 `memory-talk` 脚本所在目录(标准模式下是 `<data_root>/.venv/bin/`,使用当前模式下是检测到的安装目录)给 `memory-talk` 创建一个 `memory.talk` 同目录软链,这样用户输 `memory.talk view ...` 跟输 `memory-talk view ...` 完全等价。详见 [软链一节](#命令别名-memorytalk-软链)。

> TTL 配置(`card.initial / factor / max`、`link.*`)setup 暂不询问,沿用 `settings.json` 默认值。需要调整请直接编辑 `settings.json` —— 这一步对绝大多数用户不必要,放在 wizard 里反而干扰。

> "只有一个选项"的 prompt 仍然出现的原因:让"这是一个可配置的层"显式化。今天 vector / relation 都只有 lancedb / sqlite,但底层存储是有抽象边界的(见 `provider/storage.py`),wizard 把这个边界暴露给用户,后续加新 provider 时也是同一套交互姿势,不用改 onboarding 体验。

### 已安装(有现有 settings.json)

进入**修改模式**:

1. 加载现有 settings.json,每个 prompt 的**默认值就是现有值**(显示在方括号里),Enter 保持不动
2. **变更检测**:wizard 跑完后跟旧 settings 做 diff
   - 没有任何字段变化 → 不重写文件,直接打"配置无变化",结束
   - 有变化 → 原子写新 settings.json
3. **embedding dim 改了** → 现有 card 的向量索引是旧 dim,**所有 hybrid 搜索都会失败**。提示用户 + 询问是否立即跑 [rebuild](rebuild.md)。
4. **server 在跑** + 任何字段变了 → 设置文件被 server 在 lifespan 启动时读过一次,运行时不重读;必须**重启 server** 才生效。提示 + 询问是否立即重启(`server stop` → `server start`)。
5. **server 在跑** + 没字段变 → 不动 server。

## 幂等保证

- `settings.json` 写入是 **atomic**(tmp 文件 → rename),Ctrl-C 不会留下半个 JSON
- 已存在的目录 / 文件 / 数据**完全不动**;sessions / cards / links 不会被 setup 触碰
- 跑 N 次 setup,只要每次回答一样,最终状态跟跑 1 次完全一致 —— 这就是"幂等"
- 中途断了(Ctrl-C / kill)→ 没写就当没跑过,**没有部分写入的中间态**

## 输出

整个 wizard 的对话过程(prompt 文字 + 用户输入回显)走 **stderr**;跑完之后的最终摘要打到 **stdout**,raw Markdown(TTY 渲染下走 rich):

````markdown
# setup · **ok**

| field | value |
|---|---|
| data_root | `/home/user/.memory-talk` |
| settings | `/home/user/.memory-talk/settings.json` |
| install_mode | standard · `/home/user/.memory-talk/.venv` |
| embedding | openai · text-embedding-v4 · dim 1024 |
| vector | lancedb |
| relation | sqlite |
| port | 7788 |
| server | started · pid 12345 |
| alias | `<data_root>/.venv/bin/memory.talk → memory-talk` |
| changed | settings.json (4 fields), server restarted |
````

约定:
- `changed` 那一行说明本次跑实际**做了什么**:
  - 首次安装:`changed | settings.json (created), dirs (sessions/, cards/, links/, vectors/, logs/), server started`
  - 修改 + 重启:`changed | settings.json (4 fields), server restarted`
  - 完全 no-op:`changed | nothing — config unchanged`
- 服务最后没启动(用户回答 no)→ `server` 行写成 `not_started · run \`memory-talk server start\` to launch`,提示下一步命令
- 摘要里追加一行 `alias` 显示软链创建结果,详见下一节。

## 命令别名:`memory.talk` 软链

setup 跑完最后一步会在 `memory-talk` 脚本所在目录创建 `memory.talk → memory-talk` 同目录软链。两个名字背后是同一个 entry point,**任意一个都能用**:

```bash
memory-talk view card_xxx       # 短横线版,Python 包惯例
memory.talk view card_xxx       # 点号版,跟项目品牌名一致
```

### 如何定位脚本目录

- **标准模式**:软链放在 `<data_root>/.venv/bin/memory.talk`,指向同目录的 `memory-talk`。**用户的 PATH 里需要有 `<data_root>/.venv/bin/`** —— setup 跑完会提示用户(若不在 PATH)在 shell rc 里加这一行:
  ```bash
  export PATH="$HOME/.memory-talk/.venv/bin:$PATH"
  ```
- **使用当前模式**:`shutil.which("memory-talk")` 拿到的路径,在**同目录**创建软链:

  | 当前安装方式 | 路径 |
  |---|---|
  | `pip install --user` | `~/.local/bin/` |
  | 在 venv 里 `pip install` | `<venv>/bin/` |
  | 全局 `pip install`(管理员) | `/usr/local/bin/` 或 `/opt/.../bin/` |

### 幂等性

- 软链已存在且指向同一个 `memory-talk` → no-op
- 软链已存在但指向**别的东西** → 提示用户、询问是否覆盖(`yes` / `no` / `skip`)
- 软链不存在 → 创建
- 同名**普通文件**已存在(不是软链) → 不动它,提示用户手动处理(避免覆盖用户其他工具)

### 没有写权限

如果脚本目录(比如系统级 `/usr/bin/`)用户没写权限,setup 不会 sudo,只**打印一行提示**:

````
不能在 /usr/bin/ 写软链(no permission)。手动创建:
  sudo ln -s /usr/bin/memory-talk /usr/bin/memory.talk
````

并把摘要表里 `alias` 写成 `skipped (no write permission)`。setup 整体仍算 ok 退出。

### Windows

软链需要管理员权限或开发者模式。setup 检测到 Windows 时**默认跳过**,在摘要里写 `skipped (windows — use a .bat or PowerShell alias instead)`。

### 卸载 / 反向

setup 不提供"删除软链"动作 —— 删一个软链是 `rm` 一行的事,不值得做成命令。

## 副作用

- 写 / 改 `<data_root>/settings.json`(atomic)
- 创建数据目录(只补缺失的,已有不动)
- (可选, 标准模式)在 `<data_root>/.venv` 创建 venv + `pip install memory-talk`
- 在 `memory-talk` 同目录创建 `memory.talk` 软链(已有指向相同目标 → no-op)
- 可选:启动 server(等价于内部调 `server start`)
- 可选:重启 server(等价于 `server stop` 再 `server start`)
- 可选:跑 rebuild(等价于内部调 `rebuild`,**仅在 embedding dim 变了的场景**)
- **不动 sessions / cards / links / events.jsonl / search_log** —— 数据是用户的,setup 不应该碰

## 错误

| 情况 | 行为 |
|---|---|
| `<data_root>` 是文件不是目录 | 报错退出,exit 1 |
| `settings.json` 是损坏的 JSON | 进入"首次安装"分支前**先**问用户:"现有 settings.json 损坏,要重新初始化吗?(yes 会备份成 settings.json.bak)" |
| openai endpoint 探针失败(401 / DNS / dim 不匹配) | 把错误回显给用户,**让用户重新填字段**,wizard 不退出 |
| user `Ctrl-C` 中途退出 | 不写入任何文件,exit 130(SIGINT 标准码) |
| v1 residue(memory.db 里有 `recall_log` 表等) | 报错退出,提示走迁移流程,**不擦除任何数据** |
| port 已被占用(start 阶段) | server 启动失败,setup 整体仍报"settings 写好了,但服务未起来",exit 1 |

## 跟其他命令的边界

- **`server start`** 已经够首次启动用 —— `setup` 是它的**超集**,把 wizard + 配置 + 启动捆在一个命令里。两条路最终落地是同一份 `settings.json`。
- **`rebuild`** 是 setup 的**可选第二步**,只在 embedding dim 改了时才被调用。手工跑 rebuild 也可以,setup 不强制。
- **`sync`** 跟 setup 无关 —— sync 是导入会话,setup 跑完后由用户自己决定何时第一次 sync。

## 推荐姿势

```bash
# 首次安装
memory-talk setup

# 后续改 embedding(比如换 model 或 endpoint)
memory-talk setup        # 进 wizard,改 embedding 那几个字段,Enter 保持其他

# 排查问题(看一眼当前配置)
memory-talk server status
```
