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
    unique: bool = False           # 唯一索引(sqlite 里 NULL 不算重复:没有值的行不受限)
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
    def not_in(self, vs): return Cond(self.name, "NOT IN", list(vs))
    def is_null(self):    return Cond(self.name, "IS NULL", None)
    def is_not_null(self): return Cond(self.name, "IS NOT NULL", None)
    def asc(self):        return Order(self.name, "ASC")
    def desc(self):       return Order(self.name, "DESC")
    # ---- SET 里的表达式:update().set(position=t.c.position + 1)(挪位置、计数器 +1 用) ----
    def __add__(self, v): return Expr(self.name, "+", v)
    def __sub__(self, v): return Expr(self.name, "-", v)
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


@dataclass(frozen=True)
class Expr:
    """「这一列 ± 一个值」,只用在 SET 里。"""
    col: str
    op: str
    value: Any


class Table:
    """表 = 列声明 + 表级选项:primary_key 是组合主键(单列主键照旧用 Column(primary=True)),indexes 是多列索引。"""

    def __init__(self, name: str, columns: Sequence[Column], primary_key: Sequence[str] = (),
                 indexes: Sequence[Sequence[str]] = ()) -> None:
        self.name = name
        self.columns = list(columns)
        self.c = _Cols(self.columns)
        self.primary_key = tuple(primary_key)
        self.indexes = [tuple(ix) for ix in indexes]
        self.json_cols = {c.name for c in columns if c.type == JSON}
        self.bool_cols = {c.name for c in columns if c.type is bool}


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

    def table(self, name: str, *columns: Column, primary_key: Sequence[str] = (),
              indexes: Sequence[Sequence[str]] = ()) -> Table:
        t = Table(name, columns, primary_key, indexes)
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
            if c.op in ("IS NULL", "IS NOT NULL"):
                parts.append(f"{c.col} {c.op}")
            elif c.op in ("IN", "NOT IN"):
                if not c.value:
                    parts.append("1 = 0" if c.op == "IN" else "1 = 1")
                    continue
                ph = ", ".join(self._placeholder(len(params) + i + 1) for i in range(len(c.value)))
                params.extend(c.value)
                parts.append(f"{c.col} {c.op} ({ph})")
            else:
                params.append(c.value)
                parts.append(f"{c.col} {c.op} {self._placeholder(len(params))}")
        return (" WHERE " + " AND ".join(parts)) if parts else ""

    def _encode(self, t: Table, row: dict) -> dict:
        return {k: (json.dumps(v, ensure_ascii=False) if k in t.json_cols and v is not None and not isinstance(v, Expr) else v)
                for k, v in row.items()}

    def _decode(self, t: Table, row: dict) -> dict:
        out = {}
        for k, v in row.items():
            if k in t.json_cols and isinstance(v, str):
                v = json.loads(v)
            elif k in t.bool_cols and v is not None:
                v = bool(v)                                   # 库里是 0 / 1,读回 bool
            out[k] = v
        return out

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
        params: list = []
        sets = []
        for k, v in changes.items():
            params.append(v.value if isinstance(v, Expr) else v)
            ph = self._placeholder(len(params))
            sets.append(f"{k} = {v.col} {v.op} {ph}" if isinstance(v, Expr) else f"{k} = {ph}")
        sql = f"UPDATE {q.table.name} SET {', '.join(sets)}" + self._compile_where(q._where, params)
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
            elif not c.nullable or c.name in t.primary_key:     # sqlite 的组合主键列允许 NULL,这里显式拦住
                d += " NOT NULL"
            defs.append(d)
        if t.primary_key:
            defs.append(f"PRIMARY KEY ({', '.join(t.primary_key)})")
        indexes = [(c.name,) for c in t.columns if c.index and not c.primary] + t.indexes
        with self._lock:
            self._conn.execute(f"CREATE TABLE IF NOT EXISTS {t.name} ({', '.join(defs)})")
            have = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({t.name})")}
            for c in t.columns:                         # 表早就建过、后来加的列:补上(只能是可空、非主键的列)
                if c.name not in have:
                    self._conn.execute(f"ALTER TABLE {t.name} ADD COLUMN {c.name} {self._type(c)}")
            for cols in indexes:
                self._conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{t.name}_{'_'.join(cols)} ON {t.name}({', '.join(cols)})")
            for c in t.columns:
                if c.unique:
                    self._conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{t.name}_{c.name} ON {t.name}({c.name})")

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
