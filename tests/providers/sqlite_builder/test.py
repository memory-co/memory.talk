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
