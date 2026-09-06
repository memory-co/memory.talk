"""bash:// —— 也是「任何 PATH 里有的命令名」的兜底:scheme 名即命令名(vim:// htop:// …)。"""
from __future__ import annotations

import shutil

from services.servers.terminal import TerminalBase


class BashServer(TerminalBase):
    name = "bash"
    description = "bash:// 以及任何 PATH 里的命令名 → tmux 会话(约定优于注册)"

    def claim_list(self) -> list[str]:
        return ["bash", "*"]

    def claims(self, scheme: str) -> bool:
        return shutil.which(scheme) is not None
