"""场景共用的小工具(conftest 里的函数导出一份,避免 import conftest)。"""
from tests.conftest import git_authors, git_log  # noqa: F401
