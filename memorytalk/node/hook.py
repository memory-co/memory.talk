"""Claude Code 的 hook 命令:把 hook 收到的事件(stdin 上的一个 JSON)加上收到的时刻,追加一行到事件文件。

    <python> hook.py <事件文件>

只碰本地文件,不走网络、不要凭证(work-node.md §5);什么都不往 stdout 写——SessionStart / UserPromptSubmit 的
stdout 会进 agent 的上下文。出了错也不拦 agent:吞掉,退出码 0。故意不 import memorytalk(快、不受包的版本影响)。
"""
import json
import os
import sys
import time


def main() -> None:
    try:
        event = json.load(sys.stdin)
        event["_ts"] = time.time_ns()
        line = (json.dumps(event, ensure_ascii=False) + "\n").encode()
        fd = os.open(sys.argv[1], os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line)                     # O_APPEND 的一次 write:几个 hook 同时写也不会交错
        finally:
            os.close(fd)
    except Exception:
        pass


if __name__ == "__main__":
    main()
