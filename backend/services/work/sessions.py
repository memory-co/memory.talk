"""会话登记:会话 id ↔ URI ↔ server ↔ cwd。唯一权威,身份脱离布局(work.md §3)。"""
from __future__ import annotations

import json

from models.work import Session
from services.store import WorksLayout, atomic_write, read_text

from .tree import now


class SessionNotFound(LookupError):
    pass


class SessionRegistry:
    def __init__(self, layout: WorksLayout) -> None:
        self.layout = layout

    def _load(self, work_id: str) -> list[Session]:
        text = read_text(self.layout.sessions_json(work_id))
        return [] if text is None else [Session(**m) for m in json.loads(text)]

    def _save(self, work_id: str, sessions: list[Session]) -> None:
        atomic_write(self.layout.sessions_json(work_id),
                     json.dumps([m.model_dump() for m in sessions], ensure_ascii=False, indent=2) + "\n")

    def list(self, work_id: str) -> list[Session]:
        return self._load(work_id)

    def get(self, work_id: str, session_id: str) -> Session:
        for m in self._load(work_id):
            if m.id == session_id:
                return m
        raise SessionNotFound(f"{work_id}/{session_id}")

    def add(self, work_id: str, uri: str, scheme: str, server: str, cwd: str | None) -> Session:
        sessions = self._load(work_id)
        n = 1 + max((int(m.id.rsplit("-s", 1)[1]) for m in sessions if m.id.rsplit("-s", 1)[-1].isdigit()), default=0)
        ts = now()
        m = Session(id=f"{work_id}-s{n}", uri=uri, scheme=scheme, server=server, cwd=cwd,
                   created_at=ts, last_attached=ts)
        sessions.append(m)
        self._save(work_id, sessions)
        return m

    def touch(self, work_id: str, session_id: str) -> Session:
        sessions = self._load(work_id)
        for i, m in enumerate(sessions):
            if m.id == session_id:
                sessions[i] = m.model_copy(update={"last_attached": now()})
                self._save(work_id, sessions)
                return sessions[i]
        raise SessionNotFound(f"{work_id}/{session_id}")

    def remove(self, work_id: str, session_id: str) -> None:
        sessions = self._load(work_id)
        if not any(m.id == session_id for m in sessions):
            raise SessionNotFound(f"{work_id}/{session_id}")
        self._save(work_id, [m for m in sessions if m.id != session_id])
