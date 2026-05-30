# upgrade

把 memorytalk 升级到 PyPI 上的最新发布。背后跑的就是 pip,但**保证用对的 pip**(下面讲)。

```bash
memory.talk upgrade                 # 交互式:展示版本对比 → 确认 → 安装
memory.talk upgrade --yes           # 直接 upgrade(scripted)
memory.talk upgrade --check         # 只查版本不安装(dry-run)
```

参数:

| 参数 | 默认 | 说明 |
|---|---|---|
| `--yes` / `-y` | 关 | 跳过 prompt,直接安装。脚本里用 |
| `--check` | 关 | 只查 current / latest,不真跑 pip |

## 行为

1. 查当前版本:`importlib.metadata.version("memorytalk")`
2. 查 PyPI 最新版本:`GET https://pypi.org/pypi/memorytalk/json` 取 `info.version`
3. 三种情况:
   - 相等 → 打印 "Already on the latest" 直接退
   - 不等 → 渲染对比 + prompt 确认(或 `--yes` 跳过)
   - PyPI 查不到(网络挂)→ 报错,提示用户走 `pip install -U` 兜底
4. `--check` 在第 3 步之后短路,不进 pip
5. 用户确认后,跑:
   ```bash
   <sys.executable> -m pip install --upgrade memorytalk
   ```
   pip 输出**直接流给用户**(看下载进度 / 依赖解析 / 警告)
6. pip 退出后,**起一个新的 Python 子进程**重查 version 验证真的换了(同进程 `importlib.metadata` 可能 cache)
7. 验证通过 → 打印 "✓ upgraded to X" + server 重启提示(server 在跑的话需重启加载新代码)

## 为什么是 `sys.executable -m pip` 而不是 `pip`

直接调 `pip` 在某些环境下会**装错地方**:

- 用户有多个 Python(系统 Python + venv + pyenv 等),shell 的 `pip` 可能不是当前运行 `memory.talk` 的那个 Python 的 pip
- 后果:pip 装完报"success",但 memory.talk 重启后还是老版本(因为 site-packages 不是同一个)

`sys.executable -m pip` 保证 pip 跑在**当前运行 memory.talk 的 Python** 上,装的就是同一个 site-packages。这也是 pip 官方推荐写法(`pip --help` 第一行)。

## 为什么验证用一个新 subprocess

`importlib.metadata.version("memorytalk")` 在同一个进程内可能 cache distribution 信息 —— pip 刚改完 site-packages,我们紧接着查可能拿到旧值。

起一个新 Python 实例 `python -c "import importlib.metadata; print(...)"` 是干净状态,**保证拿到 post-install 的真实版本**。

## 输出示例

### 已最新

```
# upgrade

- package: `memorytalk`
- current: `0.5.1`
- latest:  `0.5.1`
- python:  `/Users/zzz/.venv/bin/python3`

Already on the latest version. Nothing to do.
```

### 有新版本(交互式)

```
# upgrade

- package: `memorytalk`
- current: `0.5.1`
- latest:  `0.5.2`
- python:  `/Users/zzz/.venv/bin/python3`

**Available**: `0.5.1` → `0.5.2`

Upgrade to 0.5.2? [y/N]: y

$ /Users/zzz/.venv/bin/python3 -m pip install --upgrade memorytalk

Collecting memorytalk
  Downloading memorytalk-0.5.2-py3-none-any.whl (123 kB)
  ...
Successfully installed memorytalk-0.5.2

✓ upgraded to 0.5.2

⚠ If the server is running, restart it to load the new code:
    memory.talk server restart
```

### `--check`

```
# upgrade

- package: `memorytalk`
- current: `0.5.1`
- latest:  `0.5.2`
- python:  `/Users/zzz/.venv/bin/python3`

**Available**: `0.5.1` → `0.5.2`

`--check` mode — not installing. Run without `--check` to upgrade.
```

## Exit codes

| 退出 | 含义 |
|---|---|
| `0` | 成功(已最新 / 升级完成 / 用户取消 / `--check`)|
| `1` | 包没装 / PyPI 不可达 / version 验证失败 |
| 非 0 (pip 的) | pip 自己失败,透传 pip 的 exit code |

## 不做的事(走 pip 自己)

- `--pre`(含 alpha/beta/rc)→ `pip install -U --pre memorytalk`
- 装指定版本 → `pip install memorytalk==0.5.0`
- 自定义 index → `pip install --index-url ... memorytalk`
- 回滚 / 重装 → `pip install --force-reinstall memorytalk`
- 升级 server 后自动重启 → 太魔法,可能撞 in-flight 请求,显式提示用户

## 跟其它命令的差别

- 不查 `~/.memory.talk/`(纯 pip 操作,跟数据无关)
- 不连 server(`server` 进程在不在跑都无所谓)
- 不读 `settings.json`
