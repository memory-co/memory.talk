"""CollectionsService:认知层。layer 由 spec 定义;对象按 path 读写;每个动作一个 `[layer]` 提交;变动投递给 manager。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import layers as layer_pkg
from config import Config
from layers._spec import LayerSpec
from models.collections import (CatalogDir, InboxItem, LayerInfo, Manager, Obj, Revision, SearchHit,
                            TreeItem)
from services.work.inbox import Inbox
from services.work.repo import WorkRepo

from .catalog import build, render
from .manager import FILE as MANAGER_FILE
from .manager import ManagerIndex, manager_path
from .repo import GuardError, Repo

SCHEMAS_DIR = "schemas"


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
        specs: dict[str, LayerSpec] = {}
        for name in names:
            if name in builtin:
                specs[name] = builtin[name]
            else:
                text = self.repo.read(f"{SCHEMAS_DIR}/{name}.yaml")
                if text is None:
                    raise CollectionsError("bad_layer", f"层 {name} 在 layers 里,但没有 {SCHEMAS_DIR}/{name}.yaml", 500)
                specs[name] = layer_pkg.from_yaml(text.decode())
        self.layers, self.order = specs, names

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
        spec = layer_pkg.from_yaml(schema_yaml)
        if spec.name != name:
            raise CollectionsError("bad_layer", f"schema 里的 layer 是 {spec.name!r},不是 {name!r}")
        # schema 文件归最底层(机制,不是证据);然后重跑 init 把新层加在最上
        self.repo.commit(self.order[0], f"[{self.order[0]}] layer: add {name}\n\n{('Reason: ' + reason) if reason else ''}".strip(),
                         {f"{SCHEMAS_DIR}/{name}.yaml": schema_yaml.encode()}, [], layer_of=self.layer_of_path)
        self.repo.ensure_layers([*self.order, name])
        self._load_layers()
        return self.layers[name].info(self.order.index(name))

    def layer_of_path(self, repo_path: str) -> str:
        """一个仓库路径归哪层:第一个带 `.<层>` 后缀的目录段说了算;都没有 → 最底层。"""
        if repo_path == "layers" or repo_path.startswith(SCHEMAS_DIR + "/"):
            return self.order[0]                      # 机制文件归最底层
        for seg in repo_path.split("/"):
            for name, spec in self.layers.items():
                if spec.suffix and seg.endswith(spec.suffix):
                    return name
        return self.order[0]

    # ================================================================ 对象

    def _view(self, spec: LayerSpec, obj: Any) -> Any:
        v = getattr(spec, "view", None)
        return v(self, "", obj) if v else obj

    def get(self, layer: str, path: str, rev: str | None = None) -> Obj:
        spec = self.layer(layer)
        data = self.repo.read(spec.body_path(path), rev)
        if data is None:
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        body = spec.parse(data)
        return Obj(layer=layer, path=path, title=spec.title_of(body, path), body=self._view(spec, body))

    def exists(self, layer: str, path: str) -> bool:
        return self.repo.exists(self.layer(layer).body_path(path))

    def list(self, layer: str, prefix: str = "") -> list[Obj]:
        spec = self.layer(layer)
        out = []
        for repo_path in self.repo.tree(prefix):
            if repo_path == "layers" or repo_path.startswith(SCHEMAS_DIR + "/") or repo_path.endswith(MANAGER_FILE):
                continue
            if spec.format == "raw" and self.layer_of_path(repo_path) != spec.name:
                continue
            path = spec.path_of(repo_path)
            if path is None:
                continue
            body = spec.parse(self.repo.read(repo_path) or b"")
            out.append(Obj(layer=layer, path=path, title=spec.title_of(body, path), body=self._view(spec, body)))
        return out

    def catalog(self, layer: str, root: str = "") -> CatalogDir:
        return build([(o.path, o.title or o.path) for o in self.list(layer)], root)

    def recall_text(self, layer: str = "card", root: str = "") -> str:
        return render(self.catalog(layer, root))

    def history(self, layer: str, path: str) -> list[Revision]:
        spec = self.layer(layer)
        if not self.exists(layer, path):
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        return self.repo.log(self.repo.layer_ref(layer), spec.obj_dir(path))

    def search(self, query: str, layer: str | None = None) -> list[SearchHit]:
        hits = []
        for h in self.repo.grep(query):
            lyr = self.layer_of_path(h.file)
            if layer and lyr != layer:
                continue
            spec = self.layers[lyr]
            path = spec.path_of(h.file) or h.file
            hits.append(SearchHit(layer=lyr, path=path, file=h.file, line=h.line, text=h.text))
        return hits

    def tree(self, path: str = "") -> list[TreeItem]:
        """浏览一个目录:对象(带后缀的目录折叠成一项)、普通目录、origin 文件。"""
        prefix = path.strip("/")
        seen: dict[str, TreeItem] = {}
        for repo_path in self.repo.tree(prefix):
            rest = repo_path[len(prefix):].lstrip("/") if prefix else repo_path
            if not rest or rest in ("layers",) or rest.startswith(SCHEMAS_DIR):
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

    # ---- 写 ----

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

    def create(self, layer: str, path: str, data: Any, reason: str, ctx: Ctx, subject: str | None = None,
               extra_trailer: str | None = None) -> Obj:
        spec = self.layer(layer)
        if self.exists(layer, path):
            raise CollectionsError("exists", f"{layer}:{path} 已存在", 409)
        try:
            content = spec.serialize(data)
        except Exception as e:
            raise CollectionsError("invalid", f"{layer} 的 schema 校验失败:{e}", 422) from None
        self.commit(layer, subject or f"write {path}", {spec.body_path(path): content}, [], reason, ctx, extra_trailer)
        return self.get(layer, path)

    def write(self, layer: str, path: str, data: Any, subject: str, reason: str, ctx: Ctx,
              extra_trailer: str | None = None) -> Obj:
        """整体重写(行为内部用)。"""
        spec = self.layer(layer)
        try:
            content = spec.serialize(data)
        except Exception as e:
            raise CollectionsError("invalid", f"{layer} 的 schema 校验失败:{e}", 422) from None
        self.commit(layer, subject, {spec.body_path(path): content}, [], reason, ctx, extra_trailer)
        return self.get(layer, path)

    def update(self, layer: str, path: str, patch: Any, reason: str, ctx: Ctx) -> Obj:
        spec = self.layer(layer)
        cur = self.repo.read(spec.body_path(path))
        if cur is None:
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        if spec.format == "raw":
            data = patch
        else:
            data = spec.parse(cur)
            data.update({k: v for k, v in (patch or {}).items() if v is not None})
        return self.write(layer, path, data, f"edit {path}", reason, ctx)

    def delete(self, layer: str, path: str, reason: str, ctx: Ctx) -> None:
        spec = self.layer(layer)
        if not self.exists(layer, path):
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        if spec.format == "raw":
            files = [path]
        else:
            files = [p for p in self.repo.tree(spec.obj_dir(path))]
        self.commit(layer, f"delete {path}", {}, files, reason, ctx)

    def act(self, layer: str, action: str, path: str, payload: dict, ctx: Ctx) -> Any:
        spec = self.layer(layer)
        fn = spec.behaviors.get(action)
        if fn is None:
            raise CollectionsError("no_action", f"层 {layer} 没有行为 {action}(有:{', '.join(sorted(spec.behaviors)) or '无'})", 404)
        return fn(self, path, payload, ctx)

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
            if spec.format == "raw":
                continue
            for o in self.list(name):
                m = self.managers.resolve(spec.obj_dir(o.path))
                if m and m.work == work:
                    out.append(TreeItem(name=o.title or o.path, path=o.path, kind="object", layer=name))
        return out

    def unmanaged(self) -> list[TreeItem]:
        out = []
        for name, spec in self.layers.items():
            if spec.format == "raw":
                continue
            for o in self.list(name):
                if self.managers.resolve(spec.obj_dir(o.path)) is None:
                    out.append(TreeItem(name=o.title or o.path, path=o.path, kind="object", layer=name))
        return out

    def _deliver(self, layer: str, files: list[str], subject: str, sha: str, ctx: Ctx) -> None:
        """变动打到 manager work 的收件箱;没人管 → home/unmanaged.jsonl;自己造成的不投给自己。"""
        seen = set()
        for f in files:
            if f == MANAGER_FILE or f.endswith("/" + MANAGER_FILE) or f == "layers" or f.startswith(SCHEMAS_DIR + "/"):
                continue                                   # 机制文件的变动不投递
            m = self.managers.resolve(f)
            spec = self.layers[layer]
            path = spec.path_of(f) or f
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
