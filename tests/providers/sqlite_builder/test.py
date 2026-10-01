"""SQLite -- DatabaseProvider chainable queries. See README.md."""
import pytest

from memorytalk.backend.providers import Column, SQLite
from memorytalk.backend.providers.db import JSON


@pytest.fixture
def db(tmp_path):
    return SQLite(tmp_path / "t.sqlite")


@pytest.fixture
def people(db):
    return db.table("people", Column("id", str, primary=True), Column("age", int, index=True),
                    Column("team", str), Column("meta", JSON))


def test_table_is_idempotent(db):
    db.table("t", Column("id", str, primary=True))
    db.table("t", Column("id", str, primary=True))          # 再声明一次不报错


def test_insert_then_select_one(people, db):
    db.insert(people).values(id="a", age=30, team="x", meta={"k": [1, 2]}).run()
    row = db.select(people).where(people.c.id == "a").one()
    assert row["age"] == 30 and row["meta"] == {"k": [1, 2]}        # JSON 列解回对象


def test_where_supports_ne_in_and_null(people, db):
    for i, team in enumerate(["x", "y", None]):
        db.insert(people).values(id=f"p{i}", age=i, team=team, meta=None).run()
    assert [r["id"] for r in db.select(people).where(people.c.team != "x").all()] == ["p1"]
    assert [r["id"] for r in db.select(people).where(people.c.id.in_(["p0", "p2"])).all()] == ["p0", "p2"]
    assert [r["id"] for r in db.select(people).where(people.c.team.is_null()).all()] == ["p2"]
    assert db.select(people).where(people.c.id.in_([])).all() == []


def test_order_limit_offset(people, db):
    for i in range(5):
        db.insert(people).values(id=f"p{i}", age=i, team="t", meta=None).run()
    rows = db.select(people).order_by(people.c.age.desc()).limit(2).offset(1).all()
    assert [r["age"] for r in rows] == [3, 2]


def test_update_returns_affected_rows(people, db):
    db.insert(people).values(id="a", age=1, team="t", meta=None).run()
    assert db.update(people).where(people.c.id == "a").set(age=2).run() == 1
    assert db.update(people).where(people.c.id == "zz").set(age=2).run() == 0
    assert db.select(people).where(people.c.id == "a").one()["age"] == 2


def test_delete_by_condition(people, db):
    db.insert(people).values(id="a", age=1, team="t", meta=None).run()
    assert db.delete(people).where(people.c.id == "a").run() == 1
    assert db.select(people).one() is None


def test_transaction_rolls_back_on_error(people, db):
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.insert(people).values(id="a", age=1, team="t", meta=None).run()
            raise RuntimeError("boom")
    assert db.select(people).all() == []


def test_values_are_bound_not_interpolated(people, db):
    db.insert(people).values(id="a'; DROP TABLE people; --", age=1, team="t", meta=None).run()
    assert db.select(people).where(people.c.id == "a'; DROP TABLE people; --").one()["age"] == 1


# ---- 表级选项:组合主键、多列索引 ----

@pytest.fixture
def cells(db):
    return db.table("cells", Column("work_id", str), Column("number", int), Column("alias", str),
                    Column("open", bool), Column("position", int),
                    primary_key=("work_id", "number"), indexes=[("work_id", "position")])


def test_composite_primary_key_rejects_duplicates(cells, db):
    import sqlite3
    db.insert(cells).values(work_id="w", number=1, alias="", open=True, position=0).run()
    db.insert(cells).values(work_id="w", number=2, alias="", open=True, position=1).run()
    db.insert(cells).values(work_id="v", number=1, alias="", open=True, position=0).run()      # 别的 work 同号可以
    with pytest.raises(sqlite3.IntegrityError):
        db.insert(cells).values(work_id="w", number=1, alias="dup", open=False, position=2).run()


def test_composite_primary_key_columns_are_not_null(cells, db):
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.insert(cells).values(work_id=None, number=1, alias="", open=True, position=0).run()


def test_multi_column_index_is_created(cells, db):
    rows = db._execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'cells'", [], fetch=True)
    assert any(r["name"] == "idx_cells_work_id_position" and "work_id, position" in r["sql"] for r in rows)


def test_bool_columns_read_back_as_bool(cells, db):
    db.insert(cells).values(work_id="w", number=1, alias="", open=False, position=0).run()
    assert db.select(cells).one()["open"] is False


def test_is_not_null_and_several_orders(people, db):
    for i, (age, team) in enumerate([(2, "b"), (1, None), (2, "a"), (1, "c")]):
        db.insert(people).values(id=f"p{i}", age=age, team=team, meta=None).run()
    rows = db.select(people).where(people.c.team.is_not_null()).order_by(people.c.age.asc(), people.c.team.desc()).all()
    assert [r["id"] for r in rows] == ["p3", "p0", "p2"]


def test_set_accepts_column_arithmetic(cells, db):
    for n in range(3):
        db.insert(cells).values(work_id="w", number=n + 1, alias="", open=True, position=n).run()
    assert db.update(cells).where(cells.c.work_id == "w", cells.c.position >= 1).set(position=cells.c.position + 1).run() == 2
    db.update(cells).where(cells.c.number == 1).set(position=cells.c.position - 0, alias="x").run()
    rows = db.select(cells).order_by(cells.c.number.asc()).all()
    assert [(r["position"], r["alias"]) for r in rows] == [(0, "x"), (2, ""), (3, "")]
