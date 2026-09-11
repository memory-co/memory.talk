"""数据库型 provider:做到 ORM 这一层——表定义 + 链式查询构造;方言在这里吸收,仓储层不写 SQL。

自己写的一层薄构造器(不依赖 SQLAlchemy)。SQLite 是第一个实现;MySQL / PostgreSQL 照同一个基类,
只需实现 _placeholder / _type / _execute 三个方言点。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

JSON = "json"          # 抽象列类型:str / int / float / bool / text / json


@dataclass(frozen=True)
class Column:
    name: str
    type: type | str = str
    primary: bool = False
    index: bool = False
    nullable: bool = True
    autoincrement: bool = False

    # ---- 条件:构造出来的对象,不拼字符串 ----
    def __eq__(self, v):  return Cond(self.name, "=", v)     # type: ignore[override]
    def __ne__(self, v):  return Cond(self.name, "!=", v)    # type: ignore[override]
    def __lt__(self, v):  return Cond(self.name, "<", v)
    def __le__(self, v):  return Cond(self.name, "<=", v)
    def __gt__(self, v):  return Cond(self.name, ">", v)
    def __ge__(self, v):  return Cond(self.name, ">=", v)
    def in_(self, vs):    return Cond(self.name, "IN", list(vs))
    def is_null(self):    return Cond(self.name, "IS NULL", None)
    def asc(self):        return Order(self.name, "ASC")
    def desc(self):       return Order(self.name, "DESC")
    __hash__ = object.__hash__


@dataclass(frozen=True)
class Cond:
    col: str
    op: str
    value: Any


@dataclass(frozen=True)
class Order:
    col: str
    dir: str


class Table:
    def __init__(self, name: str, columns: Sequence[Column]) -> None:
        self.name = name
        self.columns = list(columns)
        self.c = _Cols(self.columns)
        self.json_cols = {c.name for c in columns if c.type == JSON}


class _Cols:
    def __init__(self, columns: Sequence[Column]) -> None:
        for c in columns:
            setattr(self, c.name, c)


# ---- 链式查询 ----

class _Query:
    def __init__(self, db: "DatabaseProvider", table: Table) -> None:
        self.db, self.table = db, table
        self._where: list[Cond] = []

    def where(self, *conds: Cond):
        self._where.extend(conds)
        return self


class Select(_Query):
    def __init__(self, db, table) -> None:
        super().__init__(db, table)
        self._order: list[Order] = []
        self._limit: int | None = None
        self._offset: int | None = None

    def order_by(self, *orders: Order):
        self._order.extend(orders)
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def offset(self, n: int):
        self._offset = n
        return self

    def all(self) -> list[dict]:
        return self.db._select(self)

    def one(self) -> dict | None:
        rows = self.limit(1).all()
        return rows[0] if rows else None


class Insert(_Query):
    def values(self, **row):
        self._row = row
        return self

    def run(self) -> Any:
        return self.db._insert(self)


class Update(_Query):
    def set(self, **changes):
        self._set = changes
        return self

    def run(self) -> int:
        return self.db._update(self)


class Delete(_Query):
    def run(self) -> int:
        return self.db._delete(self)


# ---- 基类 ----

class DatabaseProvider:
    family = "db"
    dialect = "?"

    def table(self, name: str, *columns: Column) -> Table:
        t = Table(name, columns)
        self.ensure_table(t)
        return t

    def select(self, table: Table) -> Select: return Select(self, table)
    def insert(self, table: Table) -> Insert: return Insert(self, table)
    def update(self, table: Table) -> Update: return Update(self, table)
    def delete(self, table: Table) -> Delete: return Delete(self, table)

    def transaction(self): raise NotImplementedError
    def ensure_table(self, t: Table) -> None: raise NotImplementedError

    # ---- 方言点 ----
    def _placeholder(self, i: int) -> str: raise NotImplementedError
    def _type(self, c: Column) -> str: raise NotImplementedError
    def _execute(self, sql: str, params: Sequence, *, fetch: bool) -> Any: raise NotImplementedError

    # ---- 编译:各方言共用 ----
    def _compile_where(self, conds: list[Cond], params: list) -> str:
        parts = []
        for c in conds:
            if c.op == "IS NULL":
                parts.append(f"{c.col} IS NULL")
            elif c.op == "IN":
                if not c.value:
                    parts.append("1 = 0")
                    continue
                ph = ", ".join(self._placeholder(len(params) + i + 1) for i in range(len(c.value)))
                params.extend(c.value)
                parts.append(f"{c.col} IN ({ph})")
            else:
                params.append(c.value)
                parts.append(f"{c.col} {c.op} {self._placeholder(len(params))}")
        return (" WHERE " + " AND ".join(parts)) if parts else ""

    def _encode(self, t: Table, row: dict) -> dict:
        return {k: (json.dumps(v, ensure_ascii=False) if k in t.json_cols and v is not None else v) for k, v in row.items()}

    def _decode(self, t: Table, row: dict) -> dict:
        return {k: (json.loads(v) if k in t.json_cols and isinstance(v, str) else v) for k, v in row.items()}

    def _select(self, q: Select) -> list[dict]:
        params: list = []
        sql = f"SELECT * FROM {q.table.name}" + self._compile_where(q._where, params)
        if q._order:
            sql += " ORDER BY " + ", ".join(f"{o.col} {o.dir}" for o in q._order)
        if q._limit is not None:
            sql += f" LIMIT {int(q._limit)}"
        if q._offset is not None:
            sql += f" OFFSET {int(q._offset)}"
        return [self._decode(q.table, r) for r in self._execute(sql, params, fetch=True)]

    def _insert(self, q: Insert) -> Any:
        row = self._encode(q.table, q._row)
        cols = list(row)
        ph = ", ".join(self._placeholder(i + 1) for i in range(len(cols)))
        sql = f"INSERT INTO {q.table.name} ({', '.join(cols)}) VALUES ({ph})"
        return self._execute(sql, [row[c] for c in cols], fetch=False)

    def _update(self, q: Update) -> int:
        changes = self._encode(q.table, q._set)
        params = list(changes.values())
        sets = ", ".join(f"{k} = {self._placeholder(i + 1)}" for i, k in enumerate(changes))
        sql = f"UPDATE {q.table.name} SET {sets}" + self._compile_where(q._where, params)
        return self._execute(sql, params, fetch=False)

    def _delete(self, q: Delete) -> int:
        params: list = []
        sql = f"DELETE FROM {q.table.name}" + self._compile_where(q._where, params)
        return self._execute(sql, params, fetch=False)


class SQLite(DatabaseProvider):
    dialect = "sqlite"

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.RLock()
        self._tx = 0

    def _placeholder(self, i: int) -> str:
        return "?"

    def _type(self, c: Column) -> str:
        if c.type in (int, bool):
            return "INTEGER"
        if c.type is float:
            return "REAL"
        return "TEXT"

    def ensure_table(self, t: Table) -> None:
        defs = []
        for c in t.columns:
            d = f"{c.name} {self._type(c)}"
            if c.primary:
                d += " PRIMARY KEY" + (" AUTOINCREMENT" if c.autoincrement else "")
            elif not c.nullable:
                d += " NOT NULL"
            defs.append(d)
        with self._lock:
            self._conn.execute(f"CREATE TABLE IF NOT EXISTS {t.name} ({', '.join(defs)})")
            for c in t.columns:
                if c.index and not c.primary:
                    self._conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{t.name}_{c.name} ON {t.name}({c.name})")

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            if self._tx == 0:
                self._conn.execute("BEGIN")
            self._tx += 1
            try:
                yield
                self._tx -= 1
                if self._tx == 0:
                    self._conn.execute("COMMIT")
            except BaseException:
                self._tx -= 1
                if self._tx == 0:
                    self._conn.execute("ROLLBACK")
                raise

    def _execute(self, sql: str, params: Sequence, *, fetch: bool) -> Any:
        with self._lock:
            cur = self._conn.execute(sql, [int(p) if isinstance(p, bool) else p for p in params])
            if fetch:
                return [dict(r) for r in cur.fetchall()]
            return cur.lastrowid if sql.startswith("INSERT") else cur.rowcount
