"""CollectionsService:认知层。层 = 一份 YAML 协议(引擎据此校验);对象 = 一个目录里的一组文件,按 path 读写;一次写 = 一批文件改动 → 层的 check → 一个 `[layer]` 提交;变动投递给 manager。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from . import layers as layer_pkg
from memorytalk.backend.config import Config
from .layers import Change, Layer
from memorytalk.backend.models.collections import (InboxItem, LayerInfo, Manager, Obj, Revision, SearchHit, TreeItem, TreeView)
from memorytalk.backend.services.work.inbox import Inbox
from memorytalk.backend.services.work.repo import WorkRepo

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


def _bytes(v: str | bytes) -> bytes:
    return v if isinstance(v, bytes) else str(v).encode()


class CollectionsService:
    def __init__(self, config: Config, work_repo: WorkRepo) -> None:
        self.config = config
        self.inbox = Inbox(work_repo)
        self.author_of = lambda name: (name, f"{name}@memory.talk") if name else None   # 由 UserService 接管
        self.repo = Repo(config.collections_dir, config.git_author_name, config.git_author_email)
        self.layers: dict[str, Layer] = {}
        self.order: list[str] = []
        self.managers = ManagerIndex(self.repo)
        self._load_layers()

    # ================================================================ 层

    def _load_layers(self) -> None:
        """内置 YAML + <home>/layers/*.yaml;collections.json 里缺的补上(一次最底层提交),多出来的(文件没了)报错。"""
        builtin = layer_pkg.load_builtin()
        known = {l.name: l for l in builtin}
        try:
            user = layer_pkg.load_user(self.config.layers_dir)
        except ValueError as e:
            raise CollectionsError("bad_layer", str(e), 500) from None
        for l in user:
            if l.name in known:
                raise CollectionsError("bad_layer", f"层名重复:{l.name}", 500)
            known[l.name] = l
        cur = self.repo.layers() or []
        names = list(cur) + [n for n in known if n not in cur]
        self.repo.ensure_layers(names, {l.name for l in builtin})
        missing = [n for n in self.repo.layers() if n not in known]
        if missing:
            raise CollectionsError("bad_layer", f"collections.json 里有层 {', '.join(missing)},但既不是内置的,{self.config.layers_dir} 下也没有它的 .yaml", 500)
        self.order = list(self.repo.layers())
        self.layers = {n: known[n] for n in self.order}

    def anchor(self) -> dict:
        """collections.json 本体。"""
        return self.repo.config()

    def anchor_history(self):
        """collections.json 的提交历史 = 层的变化史(在最底层分支上)。"""
        return self.repo.log(self.repo.layer_ref(self.order[0]), CONFIG_FILE)

    def layer(self, name: str) -> Layer:
        try:
            return self.layers[name]
        except KeyError:
            raise CollectionsError("no_layer", f"没有这一层:{name}(有:{', '.join(self.order)})", 404) from None

    def _info(self, layer: Layer, order: int) -> LayerInfo:
        return LayerInfo(name=layer.name, order=order, builtin=layer.builtin, suffix=layer.suffix,
                         description=layer.description, protocol=layer.to_dict())

    def layer_infos(self) -> list[LayerInfo]:
        return [self._info(self.layers[n], i) for i, n in enumerate(self.order)]

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

    def _files(self, spec: Layer, path: str, rev: str | None = None) -> dict[str, bytes] | None:
        """一个对象目录里的文件 {相对路径: 内容};机制文件不算。不存在 → None。"""
        if spec.suffix is None:
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

    def _obj(self, spec: Layer, path: str, files: dict[str, bytes]) -> Obj:
        title = path.rsplit("/", 1)[-1]
        if spec.suffix is None:
            return Obj(layer=spec.name, path=path, title=title, content=files[""].decode("utf-8", "replace"))
        return Obj(layer=spec.name, path=path, title=title,
                   files={rel: data.decode("utf-8", "replace") for rel, data in sorted(files.items())})

    def get(self, layer: str, path: str, rev: str | None = None) -> Obj:
        spec = self.layer(layer)
        files = self._files(spec, path, rev)
        if files is None:
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        return self._obj(spec, path, files)

    def exists(self, layer: str, path: str) -> bool:
        return self._files(self.layer(layer), path) is not None

    def list(self, layer: str, prefix: str = "") -> list[Obj]:
        spec = self.layer(layer)
        out = []
        if spec.suffix is None:
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

    def _context(self, path: str) -> tuple[Layer | None, str, str]:
        """一个目录在哪:(所在对象的层, 对象 path, 对象目录内的相对路径);不在对象里 → (None, '', '')。"""
        for name in self.order:
            spec = self.layers[name]
            if spec.raw:
                continue
            got = spec.split(path)
            if got:
                return spec, got[0], got[1]
        return None, "", ""

    def tree(self, path: str = "", candidate: str | None = None, layer: str | None = None, recursive: bool = False) -> TreeView:
        """浏览一个目录:有什么(items)+ 还能建什么(can_create)+ 这个名字行不行(candidate)。
        layer= 只留那一层的对象 / 文件;recursive=1 往下走到底,items 拍平(不列目录)。"""
        prefix = path.strip("/")
        if layer:
            self.layer(layer)
        seen: dict[str, TreeItem] = {}
        for repo_path in self.repo.tree(prefix):
            rest = repo_path[len(prefix):].lstrip("/") if prefix else repo_path
            if not rest or repo_path == CONFIG_FILE or repo_path.endswith(MANAGER_FILE):
                continue
            segs = rest.split("/")
            obj_i = next((i for i, seg in enumerate(segs) if any(s.suffix and seg.endswith(s.suffix) for s in self.layers.values())), None)
            if recursive:
                if obj_i is not None:
                    head = "/".join(segs[: obj_i + 1])
                    kind, name = "object", segs[obj_i]
                else:
                    head, kind, name = rest, "file", segs[-1]
            else:
                head, kind, name = segs[0], ("object" if obj_i == 0 else "dir" if len(segs) > 1 else "file"), segs[0]
            if head in seen:
                continue
            full = f"{prefix}/{head}" if prefix else head
            if kind == "object":
                lyr = next(n for n, s in self.layers.items() if s.suffix and name.endswith(s.suffix))
                item = TreeItem(name=name, path=full[: -len(self.layers[lyr].suffix)], kind="object", layer=lyr)
            elif kind == "dir":
                item = TreeItem(name=name, path=full, kind="dir")
            else:
                item = TreeItem(name=name, path=full, kind="file", layer=self.order[0])
            if layer and item.kind != "dir" and item.layer != layer:
                continue
            seen[head] = item
        items = sorted(seen.values(), key=lambda i: (i.kind != "dir", i.path))
        spec, obj_path, rel_dir = self._context(prefix)
        view = TreeView(path=prefix, layer=spec.name if spec else None, items=items)
        if spec:                                                              # 对象目录(或它的子目录):按这一层的文件种类回答
            existing = sorted(self._files(spec, obj_path) or {})
            view.can_create = {"objects": [], "files": spec.can_create_files(rel_dir, existing)}
            if candidate is not None:
                rel = candidate.strip("/")
                kind = spec.kind_of(rel)
                exists = rel in existing
                if kind is None:
                    view.candidate = {"name": rel, "matches": None, "can": False, "reason": f"不匹配 {spec.name} 的任何一种文件"}
                elif exists:
                    view.candidate = {"name": rel, "matches": {"pattern": kind.pattern, "label": kind.label}, "exists": True, "can": False, "reason": "已存在"}
                elif kind.fixed and any(kind.match(p) for p in existing):
                    view.candidate = {"name": rel, "matches": {"pattern": kind.pattern, "label": kind.label}, "exists": False, "can": False, "reason": "固定文件,已存在"}
                else:
                    view.candidate = {"name": rel, "matches": {"pattern": kind.pattern, "label": kind.label}, "exists": False, "can": True}
            return view
        objects = []                                                          # 普通目录:按每一层的 object 规则回答
        for name in self.order:
            lyr = self.layers[name]
            if lyr.raw:
                continue
            item = {"layer": name} | lyr.object.to_dict()                     # type: ignore[union-attr]
            if lyr.object.under_regex.fullmatch(prefix):                      # type: ignore[union-attr]
                item["can"] = True
            else:
                item |= {"can": False, "reason": f"{name} 不允许放在这里(under: {lyr.object.under})"}   # type: ignore[union-attr]
            objects.append(item)
        view.can_create = {"objects": objects, "files": [{"layer": self.order[0], "can": True}]}
        if candidate is not None:
            dirname = candidate.strip("/")
            hit = next((l for l in self.layers.values() if not l.raw and l.object.regex.fullmatch(dirname)), None)  # type: ignore[union-attr]
            if hit is None:
                view.candidate = {"name": dirname, "matches": None, "can": False, "reason": "不匹配任何一层的对象目录名"}
            else:
                obj_name = hit.object.regex.fullmatch(dirname).group("name")   # type: ignore[union-attr]
                full = f"{prefix}/{obj_name}" if prefix else obj_name
                why = hit.check_object_path(full, inside_object=False)
                exists = self.exists(hit.name, full)
                view.candidate = {"name": dirname, "matches": {"layer": hit.name, "name": obj_name}, "exists": exists,
                                  "can": why is None and not exists, **({"reason": why or "已存在"} if why or exists else {})}
        return view

    # ---- 写:一次写 = 对一个对象目录的一批文件改动 → 层的 check(diff, after) → 一个 [layer] 提交 ----

    def _message(self, layer: str, subject: str, reason: str, ctx: Ctx) -> str:
        trailers = []
        if reason:
            trailers.append(f"Reason: {reason}")
        if ctx.work:
            trailers.append(f"Work: {ctx.work}")
        return f"[{layer}] {subject}" + ("\n\n" + "\n".join(trailers) if trailers else "")

    def commit(self, layer: str, subject: str, puts: dict[str, bytes], deletes: list[str], reason: str, ctx: Ctx) -> str:
        try:
            sha = self.repo.commit(layer, self._message(layer, subject, reason, ctx), puts, deletes,
                                   layer_of=self.layer_of_path, author=self.author_of(ctx.user))
        except GuardError as e:
            raise CollectionsError("guard", str(e), e.status) from None
        self._deliver(layer, list(puts) + list(deletes), subject, sha, ctx)
        return sha

    def put(self, layer: str, path: str, files: dict[str, str | bytes | None], reason: str, ctx: Ctx,
            subject: str | None = None, dry_run: bool = False) -> str:
        """对象目录的一批文件改动(值为 None = 删)→ 算 diff → 层的 check → 不过 422(带理由);过了一次 [layer] 提交。
        dry_run:只校验不提交,返回 ''。origin:files = {"": 内容}。"""
        spec = self.layer(layer)
        path = path.strip("/")
        if not path:
            raise CollectionsError("invalid", "path 不能为空", 400)
        if spec.suffix is None:
            content = files.get("")
            if content is None:
                raise CollectionsError("invalid", "origin 要有 content", 400)
            if self._context(path)[0] is not None:
                raise CollectionsError("invalid", f"{path} 在一个对象目录里,不是 origin 文件", 400)
            return "" if dry_run else self.commit(layer, subject or f"write {path}", {path: _bytes(content)}, [], reason, ctx)
        cur = self._files(spec, path) or {}
        if not cur and (why := spec.check_object_path(path, inside_object=self._context(path.rsplit("/", 1)[0] if "/" in path else "")[0] is not None)):
            raise CollectionsError("invalid", f"[{layer}] {path}:{why}", 422)
        after = dict(cur)
        changes: list[Change] = []
        for rel, content in files.items():
            rel = rel.strip("/")
            if not rel or rel == MANAGER_FILE or ".." in rel.split("/"):
                raise CollectionsError("invalid", f"文件名不合法:{rel!r}", 400)
            new = None if content is None else _bytes(content)
            if cur.get(rel) == new and (rel in cur or new is None):
                continue                                   # 没变
            changes.append(Change(rel, cur.get(rel), new))
            if new is None:
                after.pop(rel, None)
            else:
                after[rel] = new
        if not changes:
            raise CollectionsError("invalid", "没有任何改动", 400)
        why = spec.check(changes, after)
        if why:
            raise CollectionsError("invalid", f"[{layer}] {path}:{why}", 422)
        if dry_run:
            return ""
        base = spec.obj_dir(path)
        puts = {f"{base}/{c.path}": c.new for c in changes if c.new is not None}
        deletes = [f"{base}/{c.path}" for c in changes if c.new is None]
        return self.commit(layer, subject or f"write {path}", puts, deletes, reason, ctx)

    def create(self, layer: str, path: str, files: dict[str, str | bytes | None], reason: str, ctx: Ctx,
               subject: str | None = None, dry_run: bool = False) -> Obj | None:
        if self.exists(layer, path):
            raise CollectionsError("exists", f"{layer}:{path} 已存在", 409)
        self.put(layer, path, files, reason, ctx, subject, dry_run)
        return None if dry_run else self.get(layer, path)

    def update(self, layer: str, path: str, files: dict[str, str | bytes | None], reason: str, ctx: Ctx,
               subject: str | None = None, dry_run: bool = False) -> Obj | None:
        if not self.exists(layer, path):
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        self.put(layer, path, files, reason, ctx, subject or f"edit {path}", dry_run)
        return None if dry_run else self.get(layer, path)

    def delete(self, layer: str, path: str, reason: str, ctx: Ctx) -> None:
        spec = self.layer(layer)
        if not self.exists(layer, path):
            raise CollectionsError("not_found", f"{layer}:{path} 不存在", 404)
        files = [path] if spec.suffix is None else [p for p in self.repo.tree(spec.obj_dir(path))]
        self.commit(layer, f"delete {path}", {}, files, reason, ctx)

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
            if spec.suffix is None:
                continue
            for o in self.list(name):
                m = self.managers.resolve(spec.obj_dir(o.path))
                if m and m.work == work:
                    out.append(TreeItem(name=o.title, path=o.path, kind="object", layer=name))
        return out

    def unmanaged(self) -> list[TreeItem]:
        out = []
        for name, spec in self.layers.items():
            if spec.suffix is None:
                continue
            for o in self.list(name):
                if self.managers.resolve(spec.obj_dir(o.path)) is None:
                    out.append(TreeItem(name=o.title, path=o.path, kind="object", layer=name))
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
