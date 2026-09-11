# providers / sqlite_builder — 数据库型 provider 的链式查询

## 这个场景在测什么
`DatabaseProvider` 做到 ORM 这一层:`table()` 用列声明建表(幂等)、`select().where().order_by().limit()`、
`insert().values()`、`update().where().set()`、`delete()`、`transaction()`;JSON 列自动编解码;
条件是构造出来的对象(`==` / `!=` / `in_` / `is_null`)不是拼字符串。SQLite 是第一个实现。

## 不在这测什么
- MySQL / PostgreSQL(没有实现)
- 仓储的表结构 → `works/`、`users/`

## fixture 来源
`tmp_path`;不起服务。
