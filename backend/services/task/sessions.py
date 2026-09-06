"""会话登记:会话 id ↔ URI ↔ server ↔ cwd。唯一权威,身份脱离布局(task.md §3)。"""
from __future__ import annotations

import json

from models.task import Session
from services.store import TasksLayout, atomic_write, read_text

from .tree import now


class SessionNotFound(LookupError):
    pass


class SessionRegistry:
    def __init__(self, layout: TasksLayout) -> None:
        self.layout = layout

    def _load(self, task_id: str) -> list[Session]:
        text = read_text(self.layout.sessions_json(task_id))
        return [] if text is None else [Session(**m) for m in json.loads(text)]

    def _save(self, task_id: str, sessions: list[Session]) -> None:
        atomic_write(self.layout.sessions_json(task_id),
                     json.dumps([m.model_dump() for m in sessions], ensure_ascii=False, indent=2) + "\n")

    def list(self, task_id: str) -> list[Session]:
        return self._load(task_id)

    def get(self, task_id: str, session_id: str) -> Session:
        for m in self._load(task_id):
            if m.id == session_id:
                return m
        raise SessionNotFound(f"{task_id}/{session_id}")

    def add(self, task_id: str, uri: str, scheme: str, server: str, cwd: str | None) -> Session:
        sessions = self._load(task_id)
        n = 1 + max((int(m.id.rsplit("-s", 1)[1]) for m in sessions if m.id.rsplit("-s", 1)[-1].isdigit()), default=0)
        ts = now()
        m = Session(id=f"{task_id}-s{n}", uri=uri, scheme=scheme, server=server, cwd=cwd,
                   created_at=ts, last_attached=ts)
        sessions.append(m)
        self._save(task_id, sessions)
        return m

    def touch(self, task_id: str, session_id: str) -> Session:
        sessions = self._load(task_id)
        for i, m in enumerate(sessions):
            if m.id == session_id:
                sessions[i] = m.model_copy(update={"last_attached": now()})
                self._save(task_id, sessions)
                return sessions[i]
        raise SessionNotFound(f"{task_id}/{session_id}")

    def remove(self, task_id: str, session_id: str) -> None:
        sessions = self._load(task_id)
        if not any(m.id == session_id for m in sessions):
            raise SessionNotFound(f"{task_id}/{session_id}")
        self._save(task_id, [m for m in sessions if m.id != session_id])
