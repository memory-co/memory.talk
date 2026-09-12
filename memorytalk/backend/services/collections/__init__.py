"""CollectionsService:认知层。layer = 目录的校验规则;对象 = 一个目录里的一组文件,按 path 读写;一次写 = 一批文件改动 + 整目录校验 + 一个 `[layer]` 提交;变动投递给 manager。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from . import layers as layer_pkg
from memorytalk.backend.config import Config
from .layers._spec import LayerSpec
from memorytalk.backend.models.collections import (CatalogDir, InboxItem, LayerInfo, Manager, Obj, Revision, SearchHit,
                            TreeItem)
from memorytalk.backend.services.work.inbox import Inbox
from memorytalk.backend.services.work.repo import WorkRepo

from .catalog import build
from .manager import FILE as MANAGER_FILE
from .manager import ManagerIndex, manager_path
from .repo import GuardError, Repo

CONFIG_FILE = "collections.json"


class CollectionsError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code, self.status = code, status


@dataclass(frozen=True)
class Ctx:
    """谁在动:人(X-Memory-Talk-User)和它所在的 work(X-Memory-Talk-Work)。"""
    user: str | None = None
    work: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class CollectionsService:
    def __init__(self, config: Config, work_repo: WorkRepo) -> None:
        self.config = config
        self.inbox = Inbox(work_repo)
        self.author_of = lambda name: (name, f"{name}@memory.talk") if name else None   # 由 UserService 接管
        self.repo = Repo(config.collections_dir, config.git_author_name, config.git_author_email)
        self.layers: dict[str, LayerSpec] = {}
        self.order: list[str] = []
        self.managers = ManagerIndex(self.repo)
        self._load_layers()

    # ================================================================ 层

    def _load_layers(self) -> None:
        builtin = {l.name: l for l in layer_pkg.BUILTIN}
        cur = self.repo.layers()
        names = list(cur) if cur else [l.name for l in layer_pkg.BUILTIN]
        for b in layer_pkg.BUILTIN:            # 内置层缺了就补上(顺序:内置在前)
            if b.name not in names:
                names.append(b.name)
        self.repo.ensure_layers(names)
        cfg = self.repo.config()
        specs: dict[str, LayerSpec] = {}
        for entry in cfg["layers"]:
            name = entry["name"]
            if name in builtin:
                specs[name] = builtin[name]
            elif "schema" in entry:
                specs[name] = layer_pkg.from_dict(name, entry["schema"])
            else:
                raise CollectionsError("bad_layer", f"collections.json 里的层 {name} 既不是内置的,也没有 schema", 500)
        self.layers, self.order = specs, [e["name"] for e in cfg["layers"]]

    def anchor(self) -> dict:
        """collections.json 本体。"""
        return self.repo.config()

    def anchor_history(self):
        """collections.json 的提交历史 = 层的变化史(在最底层分支上)。"""
        return self.repo.log(self.repo.layer_ref(self.order[0]), CONFIG_FILE)

    def layer(self, name: str) -> LayerSpec:
        try:
            return self.layers[name]
        except KeyError:
            raise CollectionsError("no_layer", f"没有这一层:{name}(有:{', '.join(self.order)})", 404) from None

    def layer_infos(self) -> list[LayerInfo]:
        return [self.layers[n].info(i) for i, n in enumerate(self.order)]

    def add_layer(self, name: str, schema_yaml: str, reason: str, ctx: Ctx) -> LayerInfo:
        if name in self.layers:
            raise CollectionsError("exists", f"层已存在:{name}", 409)
        schema = layer_pkg.schema_from_yaml(schema_yaml)
        if schema.get("layer", name) != name:
            raise CollectionsError("bad_layer", f"schema 里的 layer 是 {schema.get('layer')!r},不是 {name!r}")
        layer_pkg.from_dict(name, schema)                     # 先校验能不能解析
        entry = {"name": name, "schema": {k: v for k, v in schema.items() if k != "layer"}, "added_at": _now()}
        msg = f"[{self.order[0]}] collections: add layer {name}" + (f"\n\nReason: {reason}" if reason else "")
        try:
            self.repo.add_layer(entry, msg, author=self.author_of(ctx.user))
        except GuardError as e:
            raise CollectionsError("guard", str(e), e.status) from None
        self._load_layers()
        return self.layers[name].info(self.order.index(name))

    def layer_of_path(self, repo_path: str) -> str:
        """一个仓库路径归哪层:第一个带 `.<层>` 后缀的目录段说了算;都没有 → 最底层。"""
        if repo_path == CONFIG_FILE:
            return self.order[0]                      # 机制文件归最底层
        for seg in repo_path.split("/"):
            for name, spec in self.layers.items():
                if spec.suffix and seg.endswith(spec.suffix):
                    return name
        return self.order[0]

    # ================================================================ 对象

    def split(self, repo_path: str) -> tuple[str, str, str]:
        """仓库路径 → (层, 对象 path, 目录内相对路径)。origin 的相对路径为 ''。"""
        layer = self.layer_of_path(repo_path)
        spec = self.layers[layer]
        got = spec.split(repo_path)
        if got is None:
            return (self.order[0], repo_path, "")
        return (layer, got[0], got[1])

    def _files(self, spec: LayerSpec, path: str, rev: str | None = None) -> dict[str, bytes] | None:
        """一个对象目录里的文件 {相对路径: 内容};机制文件不算。不存在 → None。"""
        if spec.raw:
            data = self.repo.read(path, rev)
            return None if data is None else {"": data}
        prefix = spec.obj_dir(path)
        out: dict[str, bytes] = {}
        for repo_path in self.repo.tree(prefix, rev):
            if not repo_path.startswith(prefix + "/"):
                continue
            rel = repo_path[len(prefix) + 1:]
            if rel == MANAGER_FILE:
                continue
            out[rel] = self.repo.read(repo_path, rev) or b""
        return out or None

    def _obj(self, spec: LayerSpec, path: str, files: dict[str, bytes]) -> Obj:
        if spec.raw:
            text = files[""].decode("utf-8", "replace")
            return Obj(layer=spec.name, path=path, title=path.rsplit("/", 1)[-1], body=text)
        parsed = spec.parse(files)
        return Obj(layer=spec.name, path=path, title=spec.title_of(parsed, path), files=sorted(files),
                   body=spec.body(parsed, path))

    def get(self, layer: str, path: str, rev: str | None = None) -> Obj:
        spec = self.layer(layer)
        files = self._files(spec, path, rev)
        if files is None:
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        return self._obj(spec, path, files)

    def file(self, layer: str, path: str, rel: str) -> bytes | None:
        """对象目录里的一个文件(行为用)。"""
        spec = self.layer(layer)
        return self.repo.read(path if spec.raw else f"{spec.obj_dir(path)}/{rel}")

    def exists(self, layer: str, path: str) -> bool:
        return self._files(self.layer(layer), path) is not None

    def list(self, layer: str, prefix: str = "") -> list[Obj]:
        spec = self.layer(layer)
        out = []
        if spec.raw:
            for repo_path in self.repo.tree(prefix):
                if repo_path == CONFIG_FILE or repo_path.endswith(MANAGER_FILE) or self.layer_of_path(repo_path) != spec.name:
                    continue
                out.append(self._obj(spec, repo_path, {"": self.repo.read(repo_path) or b""}))
            return out
        seen: set[str] = set()
        for repo_path in self.repo.tree(prefix):
            got = spec.split(repo_path)
            if got is None or got[0] in seen or self.layer_of_path(repo_path) != spec.name:
                continue
            seen.add(got[0])
            out.append(self.get(layer, got[0]))
        return out

    def catalog(self, layer: str, root: str = "") -> CatalogDir:
        return build([(o.path, o.title or o.path) for o in self.list(layer)], root)

    def history(self, layer: str, path: str) -> list[Revision]:
        spec = self.layer(layer)
        if not self.exists(layer, path):
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        return self.repo.log(self.repo.layer_ref(layer), spec.obj_dir(path))

    def search(self, query: str, layer: str | None = None) -> list[SearchHit]:
        hits = []
        for h in self.repo.grep(query):
            lyr, path, _ = self.split(h.file)
            if layer and lyr != layer:
                continue
            hits.append(SearchHit(layer=lyr, path=path, file=h.file, line=h.line, text=h.text))
        return hits

    def tree(self, path: str = "") -> list[TreeItem]:
        """浏览一个目录:对象(带后缀的目录折叠成一项)、普通目录、origin 文件。"""
        prefix = path.strip("/")
        seen: dict[str, TreeItem] = {}
        for repo_path in self.repo.tree(prefix):
            rest = repo_path[len(prefix):].lstrip("/") if prefix else repo_path
            if not rest or rest == CONFIG_FILE:
                continue
            head = rest.split("/", 1)[0]
            full = f"{prefix}/{head}" if prefix else head
            if head in seen:
                continue
            obj_layer = next((n for n, s in self.layers.items() if s.suffix and head.endswith(s.suffix)), None)
            if obj_layer:
                seen[head] = TreeItem(name=head, path=full[: -len(self.layers[obj_layer].suffix)], kind="object", layer=obj_layer)
            elif "/" in rest:
                seen[head] = TreeItem(name=head, path=full, kind="dir")
            elif head != MANAGER_FILE:
                seen[head] = TreeItem(name=head, path=full, kind="file", layer=self.order[0])
        return sorted(seen.values(), key=lambda i: (i.kind != "dir", i.name))

    # ---- 写:一次写 = 对一个对象目录的一批文件改动,整目录按层的 schema 校验,过了一次 [layer] 提交 ----

    def _message(self, layer: str, subject: str, reason: str, ctx: Ctx, extra: str | None) -> str:
        trailers = []
        if reason:
            trailers.append(f"Reason: {reason}")
        if ctx.work:
            trailers.append(f"Work: {ctx.work}")
        if extra:
            trailers.append(extra)
        return f"[{layer}] {subject}" + ("\n\n" + "\n".join(trailers) if trailers else "")

    def commit(self, layer: str, subject: str, puts: dict[str, bytes], deletes: list[str], reason: str, ctx: Ctx,
               extra_trailer: str | None = None) -> str:
        try:
            sha = self.repo.commit(layer, self._message(layer, subject, reason, ctx, extra_trailer), puts, deletes,
                                   layer_of=self.layer_of_path, author=self.author_of(ctx.user))
        except GuardError as e:
            raise CollectionsError("guard", str(e), e.status) from None
        self._deliver(layer, list(puts) + list(deletes), subject, sha, ctx)
        return sha

    @staticmethod
    def _bytes(v: str | bytes) -> bytes:
        return v if isinstance(v, bytes) else str(v).encode()

    def put(self, layer: str, path: str, files: dict[str, str | bytes | None], reason: str, ctx: Ctx,
            subject: str | None = None, extra_trailer: str | None = None) -> str:
        """对象目录的一批文件改动:值为 None = 删。改完的目录整个按 schema 校验,不过 422;过了一次 [layer] 提交。
        origin:files = {"": 内容}。"""
        spec = self.layer(layer)
        path = path.strip("/")
        if not path:
            raise CollectionsError("invalid", "path 不能为空", 400)
        if spec.raw:
            content = files.get("")
            if content is None:
                raise CollectionsError("invalid", "origin 要有 content", 400)
            return self.commit(layer, subject or f"write {path}", {path: self._bytes(content)}, [], reason, ctx, extra_trailer)
        cur = self._files(spec, path) or {}
        new = dict(cur)
        for rel, content in files.items():
            rel = rel.strip("/")
            if not rel or rel == MANAGER_FILE or ".." in rel.split("/"):
                raise CollectionsError("invalid", f"文件名不合法:{rel!r}", 400)
            if content is None:
                new.pop(rel, None)
            else:
                new[rel] = self._bytes(content)
        try:
            spec.validate(new)
        except ValueError as e:
            raise CollectionsError("invalid", f"{layer} 的 schema 校验失败:{e}", 422) from None
        base = spec.obj_dir(path)
        puts = {f"{base}/{rel}": data for rel, data in new.items() if cur.get(rel) != data}
        deletes = [f"{base}/{rel}" for rel in cur if rel not in new]
        return self.commit(layer, subject or f"write {path}", puts, deletes, reason, ctx, extra_trailer)

    def files_from_data(self, layer: str, path: str, data: dict, merge: bool) -> dict[str, bytes]:
        """`data` 简写 → 文件:只对「唯一一个带字段的固定文件」的层成立(card、单文件用户层)。"""
        spec = self.layer(layer)
        rule = spec.fielded_file
        if rule is None:
            raise CollectionsError("invalid", f"层 {layer} 不接受 data 简写,请用 files 给出目录里的文件", 400)
        obj = dict(data or {})
        if merge:
            cur = self.file(layer, path, rule.pattern)
            if cur is not None:
                base = rule.parse(cur)
                base.update({k: v for k, v in obj.items() if v is not None})
                obj = base
        try:
            return {rule.pattern: rule.serialize(obj)}
        except Exception as e:
            raise CollectionsError("invalid", f"{layer} 的 schema 校验失败:{rule.pattern}:{e}", 422) from None

    def create(self, layer: str, path: str, files: dict[str, str | bytes], reason: str, ctx: Ctx,
               subject: str | None = None, extra_trailer: str | None = None) -> Obj:
        spec = self.layer(layer)
        if self.exists(layer, path):
            raise CollectionsError("exists", f"{layer}:{path} 已存在", 409)
        full: dict[str, str | bytes | None] = {} if spec.raw else dict(spec.defaults())
        full.update(files)
        self.put(layer, path, full, reason, ctx, subject, extra_trailer)
        return self.get(layer, path)

    def update(self, layer: str, path: str, files: dict[str, str | bytes | None], reason: str, ctx: Ctx) -> Obj:
        if not self.exists(layer, path):
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        self.put(layer, path, files, reason, ctx, f"edit {path}")
        return self.get(layer, path)

    def delete(self, layer: str, path: str, reason: str, ctx: Ctx) -> None:
        spec = self.layer(layer)
        if not self.exists(layer, path):
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        files = [path] if spec.raw else [p for p in self.repo.tree(spec.obj_dir(path))]
        self.commit(layer, f"delete {path}", {}, files, reason, ctx)

    def act(self, layer: str, action: str, path: str, payload: dict, ctx: Ctx) -> Any:
        spec = self.layer(layer)
        fn = spec.behaviors.get(action)
        if fn is None:
            raise CollectionsError("no_action", f"层 {layer} 没有行为 {action}(有:{', '.join(sorted(spec.behaviors)) or '无'})", 404)
        if not spec.raw and not self.exists(layer, path):
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        try:
            return fn(self, path, payload, ctx)
        except KeyError as e:
            raise CollectionsError("invalid", f"行为 {action} 缺参数 {e.args[0]!r}", 422) from None

    # ================================================================ manager

    def _as_dir(self, path: str) -> str:
        """对象 path → 它的目录(带后缀);普通目录 / 文件原样。"""
        path = path.strip("/")
        for name, spec in self.layers.items():
            if spec.suffix and not path.endswith(spec.suffix) and self.exists(name, path):
                return spec.obj_dir(path)
        return path

    def manager(self, path: str) -> Manager | None:
        return self.managers.resolve(self._as_dir(path))

    def set_manager(self, dir_: str, work: str, reason: str, ctx: Ctx) -> Manager:
        dir_ = self._as_dir(dir_)
        file = manager_path(dir_)
        layer = self.layer_of_path(file)
        self.commit(layer, f"manage {dir_ or '/'} by {work}", {file: (json.dumps({"work": work}) + "\n").encode()}, [], reason, ctx)
        return Manager(dir=dir_, work=work)

    def unset_manager(self, dir_: str, reason: str, ctx: Ctx) -> None:
        dir_ = self._as_dir(dir_)
        file = manager_path(dir_)
        if not self.repo.exists(file):
            raise CollectionsError("not_found", f"{file} 不存在", 404)
        self.commit(self.layer_of_path(file), f"unmanage {dir_ or '/'}", {}, [file], reason, ctx)

    def managed_by(self, work: str) -> list[TreeItem]:
        """这个 work 管的所有对象(按 manager 继承链解析)。"""
        out = []
        for name, spec in self.layers.items():
            if spec.raw:
                continue
            for o in self.list(name):
                m = self.managers.resolve(spec.obj_dir(o.path))
                if m and m.work == work:
                    out.append(TreeItem(name=o.title or o.path, path=o.path, kind="object", layer=name))
        return out

    def unmanaged(self) -> list[TreeItem]:
        out = []
        for name, spec in self.layers.items():
            if spec.raw:
                continue
            for o in self.list(name):
                if self.managers.resolve(spec.obj_dir(o.path)) is None:
                    out.append(TreeItem(name=o.title or o.path, path=o.path, kind="object", layer=name))
        return out

    def _deliver(self, layer: str, files: list[str], subject: str, sha: str, ctx: Ctx) -> None:
        """变动打到 manager work 的收件箱;没人管 → home/unmanaged.jsonl;自己造成的不投给自己。"""
        seen = set()
        for f in files:
            if f == MANAGER_FILE or f.endswith("/" + MANAGER_FILE) or f == CONFIG_FILE:
                continue                                   # 机制文件的变动不投递
            m = self.managers.resolve(f)
            _, path, _ = self.split(f)
            key = (path, m.work if m else None)
            if key in seen:
                continue
            seen.add(key)
            item = InboxItem(ts=_now(), layer=layer, path=path, subject=subject, sha=sha, by=ctx.user,
                             routed_by=m.dir if m else "")
            if m is None:
                self.inbox.put_unmanaged(item)
            elif m.work != ctx.work:
                self.inbox.put(m.work, item)


__all__ = ["CollectionsService", "CollectionsError", "Ctx"]
