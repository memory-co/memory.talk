# services/auth —— 门

先立 admin,再进门(设计:[auth.md](../../../../docs/designs/v5/auth.md))。`main.py` 里的中间件靠它把每个请求的 token 变成名字。

| 文件 | 重点 |
|---|---|
| `__init__.py` | `AuthService(users, tokens)`:`setup_required()`(没有 `admin` 账号)/ `setup(req)`(建 admin 并发 token,只能一次)/ `login(name, password)` / `issue(name)`(发随机 token,只存 sha256)/ `resolve(token)`(token → 名字,不认识给 None)/ `logout(token)` / `revoke_all(name)` / `set_password(name, new, old, check_old)`(改完作废这个人的全部 token)。`hash_password` / `verify_password` 用标准库 `hashlib.scrypt`,格式 `scrypt$<salt>$<hash>`。`AuthError(code, message, status)` 映射成 401 / 403 / 404 |
| `repo.py` | `TokenRepo` 接口(`get` / `put` / `delete` / `list`,键是 token 的哈希)+ `FsTokenRepo`(`auth/tokens/<sha256>.json`)+ `DbTokenRepo`(`auth_tokens` 表);`make_token_repo(store)` 按族选 |

密码哈希存在 user 的记录里(`users/repo.py`),这里只管 token。
