"""各家读取器共用的几样:中心给的说明(Spec)、读一步交回的一批(Batch)、从游标读完整的行(read_lines)。

读取器的约定(claude.py、bash.py):
    Reader.restored(spec, cursors)   从中心存的游标恢复(没有就从头读)
    reader.step(finish=None)         读一步,交回一批;不改自己的状态。finish = (原因, status):读到头了就把开着的段按它结束
    reader.commit(batch)             推成功了才调:状态往前挪,用完的文件删掉
    reader.rebase(spec)              中心又说了一次 watch(重入开了新的 worklet 段 / 现场重开了)
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

from . import otlp


@dataclass
class Spec:
    """中心让节点盯一个工作单元时给的说明(watch)。"""
    work_id: str
    worklet_id: str
    trace_id: str
    parent: str                         # 这个工作单元现在开着的那段 worklet 段:会话段挂在它下面
    hooks: str                          # 事件文件(claude 的 hooks、bash 的命令事件)
    transcripts: str = ""               # 会话记录根(claude:~/.claude/projects;bash 没有)
    session_id: str | None = None       # 开现场时钉住的会话 id(claude)
    server: str = "claude"
    cwd: str | None = None
    tmux_socket: str | None = None      # 看现场活没活着:tmux -L <它>
    since: int = 0                      # 工作单元打开的时刻(Unix 纳秒)

    @classmethod
    def of(cls, d: dict) -> "Spec":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})

    def dump(self) -> dict:
        return asdict(self)


@dataclass
class Batch:
    spans: dict[str, dict] = field(default_factory=dict)       # span id → 这一步结束时它的样子(开着的合并属性,结束的定稿)
    records: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    drained: bool = True                                       # 来源都读到头了
    cleanup: list[str] = field(default_factory=list)           # 推成功以后可以删的文件(bash 每条命令的输出)

    def empty(self) -> bool:
        return not self.spans and not self.records

    def cursors(self, worklet_id: str) -> list[dict]:
        """推到哪了:事件文件和每份会话记录各一行(给人看的),reader 一行是整个状态(重启用它)。"""
        st = self.state
        rows = [{"worklet_id": worklet_id, "source": "hooks", "position": str(st["hooks"])}]
        rows += [{"worklet_id": worklet_id, "source": sid, "position": str(f["offset"])} for sid, f in st.get("files", {}).items()]
        rows.append({"worklet_id": worklet_id, "source": "reader", "position": json.dumps(st, ensure_ascii=False)})
        return rows

    def document(self) -> dict:
        return otlp.document(list(self.spans.values()), self.records)


def saved_state(cursors: list[dict]) -> dict | None:
    """中心存的 reader 那一行(整个状态);没有就是 None。"""
    for c in cursors:
        if c["source"] == "reader":
            return json.loads(c["position"])
    return None


def read_lines(path: str, offset: int, budget: int) -> tuple[list[tuple[int, int, dict | None]], bool]:
    """从 offset 读到现在为止完整的行(最后半行不要,下次再读);一次最多 budget 字节,但至少一整行。
    交回 ([(行首, 行尾的下一个字节, 解出来的 JSON 或 None)], 读没读到头)。"""
    try:
        with open(path, "rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            if size <= offset:
                return [], True
            fh.seek(offset)
            data = fh.read(min(size - offset, budget))
            if b"\n" not in data and offset + len(data) < size:
                data += fh.readline()                          # 一行比预算还大:整行读完
    except FileNotFoundError:
        return [], True
    out, pos = [], 0
    while (nl := data.find(b"\n", pos)) >= 0:
        raw = data[pos:nl]
        try:
            d = json.loads(raw) if raw.strip() else None
        except ValueError:
            d = None
        out.append((offset + pos, offset + nl + 1, d if isinstance(d, dict) else None))
        pos = nl + 1
    return out, offset + len(data) >= size
