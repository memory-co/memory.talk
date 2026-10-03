"""节点目录里放什么(<home>/node/):

    node.sock                       中心 → 节点的控制口(watch / flush / list)
    node.json                       节点进程的 pid(memory.talk node start / stop 用)
    worklets/<worklet id>/
        watch.json                  盯着它的那份说明(节点重启后接着盯)
        hooks.jsonl                 事件,一行一个(只追加;推成功了游标才往前挪):claude 的 hooks,或 bash 的命令事件
        settings.json               claude --settings:注入的 hooks
        bashrc                      bash --rcfile:先读用户自己的 ~/.bashrc,再装上记命令的钩子
        cur / out/<时刻>.txt        bash:正在跑的那条命令从哪一行开始 / 每条命令的输出(进了 trace 就删)
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

HOOK_SCRIPT = Path(__file__).with_name("hook.py")
CLAUDE_HOOK_EVENTS = ("SessionStart", "SessionEnd", "UserPromptSubmit", "Stop", "Notification", "PreToolUse", "PostToolUse")


def worklet_dir(node_dir: Path, worklet_id: str) -> Path:
    return Path(node_dir) / "worklets" / worklet_id


def hooks_file(node_dir: Path, worklet_id: str) -> Path:
    return worklet_dir(node_dir, worklet_id) / "hooks.jsonl"


def watch_file(node_dir: Path, worklet_id: str) -> Path:
    return worklet_dir(node_dir, worklet_id) / "watch.json"


def claude_settings(node_dir: Path, worklet_id: str) -> Path:
    """写出 claude --settings 用的文件:几个 hook 都跑同一条命令,把事件追加到这个工作单元的 hooks.jsonl。
    --settings 是在用户自己的设置之上「加」,用户原有的 hooks 照跑。交回文件路径。"""
    d = worklet_dir(node_dir, worklet_id)
    d.mkdir(parents=True, exist_ok=True)
    command = shlex.join([sys.executable, str(HOOK_SCRIPT), str(hooks_file(node_dir, worklet_id))])
    hooks = {event: [{"hooks": [{"type": "command", "command": command}]}] for event in CLAUDE_HOOK_EVENTS}
    path = d / "settings.json"
    path.write_text(json.dumps({"hooks": hooks}, ensure_ascii=False, indent=2))
    return path


BASHRC = r"""# memory.talk:这个 bash 的「记录」(docs/designs/v5/work-server-io.md §6)。bash server 开现场时生成,别手改——下次开会重写。
# 每条命令执行前(PS0)、回到提示符前(PROMPT_COMMAND)各记一行事件;输出是这条命令那一段屏幕(tmux capture-pane,渲染好的文字)。
# 节点读了推进 trace。命令前加一个空格 = 不进历史,也不进记录(原文和输出都不记)。
[ -f ~/.bashrc ] && . ~/.bashrc
__mt_events=@EVENTS@
__mt_outdir=@OUTDIR@
__mt_cur=@CUR@
case ":${HISTCONTROL:-}:" in *ignorespace*|*ignoreboth*) HISTCONTROL=ignorespace ;; *) HISTCONTROL= ;; esac   # 重复的命令也进历史,才认得出来
__mt_q() {   # $1 = 变量名,$2 = 文本 → JSON 字符串
  local s=$2
  s=${s//\\/\\\\}; s=${s//\"/\\\"}; s=${s//$'\n'/\\n}; s=${s//$'\r'/\\r}; s=${s//$'\t'/\\t}; s=${s//[[:cntrl:]]/}
  printf -v "$1" '"%s"' "$s"
}
__mt_ns() { printf -v "$1" '%s000' "${EPOCHREALTIME//[.,]/}"; }
__mt_preexec() {   # PS0 的命令替换里跑(子 shell):命令开始,什么都不往终端写
  local h num cmd= hidden= hj=false now pos q w
  h=$(HISTTIMEFORMAT= builtin history 1)
  [[ $h =~ ^[[:space:]]*([0-9]+)[*]?[[:space:]]+(.*)$ ]] && num=${BASH_REMATCH[1]} cmd=${BASH_REMATCH[2]}
  if [ -z "$num" ] || [ "$num" = "$__mt_hist" ]; then hidden=1 hj=true cmd=; fi   # 没进历史:前面加了空格
  pos=$(tmux display -p -t "$TMUX_PANE" '#{e|+:#{history_size},#{cursor_y}}' 2>/dev/null)
  __mt_ns now; __mt_q q "$cmd"; __mt_q w "$PWD"
  printf '%s %s\n' "${pos:-0}" "${hidden:-0}" 2>/dev/null > "$__mt_cur"
  printf '{"e":"cmd","ts":%s,"cmd":%s,"cwd":%s,"hidden":%s}\n' "$now" "$q" "$w" "$hj" 2>/dev/null >> "$__mt_events"
}
__mt_precmd() {   # 回到提示符之前:命令结束,取它那一段屏幕
  local code=$? from hidden now hs cy cx last s e out= w o
  if [ -f "$__mt_cur" ] && read -r from hidden < "$__mt_cur"; then
    rm -f "$__mt_cur"
    __mt_ns now
    read -r hs cy cx < <(tmux display -p -t "$TMUX_PANE" '#{history_size} #{cursor_y} #{cursor_x}' 2>/dev/null)
    if [ "$hidden" = 0 ] && [ -n "$hs" ]; then
      last=$((hs + cy)); [ "${cx:-0}" -gt 0 ] || last=$((last - 1))
      if [ "$last" -ge "$from" ]; then
        s=$((from - hs)); e=$((last - hs)); [ "$s" -lt "-$hs" ] && s=-
        out="$__mt_outdir/$now.txt"
        tmux capture-pane -p -J -t "$TMUX_PANE" -S "$s" -E "$e" 2>/dev/null > "$out" || out=
      fi
    fi
    __mt_q w "$PWD"; __mt_q o "$out"
    printf '{"e":"done","ts":%s,"code":%s,"cwd":%s,"out":%s}\n' "$now" "$code" "$w" "$o" 2>/dev/null >> "$__mt_events"
  fi
  __mt_hist=$(HISTTIMEFORMAT= builtin history 1); [[ $__mt_hist =~ ^[[:space:]]*([0-9]+) ]] && __mt_hist=${BASH_REMATCH[1]}
  return $code
}
PS0='$(__mt_preexec)'"${PS0:-}"
if [[ "$(declare -p PROMPT_COMMAND 2>/dev/null)" == "declare -a"* ]]; then PROMPT_COMMAND=(__mt_precmd "${PROMPT_COMMAND[@]}")
else PROMPT_COMMAND="__mt_precmd${PROMPT_COMMAND:+;$PROMPT_COMMAND}"; fi
__mt_ns __mt_t0; __mt_q __mt_w0 "$PWD"
printf '{"e":"start","ts":%s,"pid":%s,"cwd":%s,"bash":"%s"}\n' "$__mt_t0" "$$" "$__mt_w0" "$BASH_VERSION" 2>/dev/null >> "$__mt_events"
unset __mt_t0 __mt_w0
"""


def bash_rc(node_dir: Path, worklet_id: str) -> Path:
    """写出 bash --rcfile 用的文件:先读用户自己的 ~/.bashrc(和直接开 bash 一个环境),再装上记命令的钩子,
    事件追加到这个工作单元的 hooks.jsonl,输出放在 out/ 下。交回文件路径。"""
    d = worklet_dir(node_dir, worklet_id)
    (d / "out").mkdir(parents=True, exist_ok=True)
    body = (BASHRC.replace("@EVENTS@", shlex.quote(str(hooks_file(node_dir, worklet_id))))
            .replace("@OUTDIR@", shlex.quote(str(d / "out"))).replace("@CUR@", shlex.quote(str(d / "cur"))))
    path = d / "bashrc"
    path.write_text(body)
    return path
