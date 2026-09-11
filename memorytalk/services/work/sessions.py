"""会话(现场)登记:会话 id ↔ URI ↔ server ↔ cwd。唯一权威,身份脱离布局(session.md)。"""
from __future__ import annotations

from memorytalk.models.work import Session

from .repo import WorkRepo
from .tree import now


class SessionNotFound(LookupError):
    pass


class SessionRegistry:
    def __init__(self, repo: WorkRepo) -> None:
        self.repo = repo

    def _load(self, work_id: str) -> list[Session]:
        return [Session(**m) for m in (self.repo.get_doc(work_id, "sessions") or [])]

    def _save(self, work_id: str, sessions: list[Session]) -> None:
        self.repo.put_doc(work_id, "sessions", [m.model_dump() for m in sessions])

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
        m = Session(id=f"{work_id}-s{n}", uri=uri, scheme=scheme, server=server, cwd=cwd, created_at=ts, last_attached=ts)
        sessions.append(m)
        self._save(work_id, sessions)
        return m

    def replace(self, work_id: str, session: Session) -> Session:
        sessions = self._load(work_id)
        for i, m in enumerate(sessions):
            if m.id == session.id:
                sessions[i] = session
                self._save(work_id, sessions)
                return session
        raise SessionNotFound(f"{work_id}/{session.id}")

    def touch(self, work_id: str, session_id: str) -> Session:
        return self.replace(work_id, self.get(work_id, session_id).model_copy(update={"last_attached": now()}))

    def remove(self, work_id: str, session_id: str) -> None:
        sessions = self._load(work_id)
        if not any(m.id == session_id for m in sessions):
            raise SessionNotFound(f"{work_id}/{session_id}")
        self._save(work_id, [m for m in sessions if m.id != session_id])
