"""memory.talk —— 跑 code agent 的工作台,记忆是它的副产物。"""
from importlib.metadata import PackageNotFoundError, version as _version
from pathlib import Path


def _from_pyproject() -> str:
    """没安装、直接从源码跑时,读仓库根 pyproject.toml 的 version。"""
    try:
        import tomllib
        with open(Path(__file__).resolve().parents[1] / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"] + "+src"
    except Exception:
        return "0.0.0+src"


try:
    __version__ = _version("memorytalk")
except PackageNotFoundError:
    __version__ = _from_pyproject()

__all__ = ["__version__"]
