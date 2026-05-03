"""CLI: filter list / run / mark / unmark.

Filter is a viewfinder: it does NOT do work. filter.py is a pure
Python module that exports ``select(client) -> list[str]``; meta.json
declares a mark_tag schema (lists of tags to add/remove). `mark`
applies the schema to specific subjects; `unmark` reverses.

filter.py runs **in-process** via importlib (no subprocess) — that
way it shares the CLI's HTTP client (and any test-time monkeypatch
of ``_make_client``), keeping the test path identical to production.

Built-in filters live in ``memorytalk/filters/`` (shipped with the
package); user filters live in ``<data_root>/filters/``. User filters
override built-ins on name conflict.
"""
from __future__ import annotations
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import click

import memorytalk
from memorytalk.cli._format import fmt_error
from memorytalk.cli._http import ApiError, api, extract_error_message
from memorytalk.cli._render import emit_json, emit_json_err, emit_md, emit_md_err
from memorytalk.config import Config


NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
BUILTIN_FILTERS_DIR = Path(memorytalk.__file__).parent / "filters"


@dataclass
class FilterInfo:
    name: str
    dir: Path
    source: str   # "builtin" or "user"
    meta: dict


# ---------- discovery / loading ----------

def _user_filters_dir(cfg: Config) -> Path:
    return cfg.data_root / "filters"


def _is_valid_filter_dir(d: Path) -> bool:
    return (d / "filter.py").is_file() and (d / "meta.json").is_file()


def _validate_meta(meta: dict) -> dict:
    if "mark_tag" not in meta or not isinstance(meta["mark_tag"], dict):
        raise ValueError("meta.json missing or invalid 'mark_tag' field")
    mt = meta["mark_tag"]
    add = mt.get("add") or []
    remove = mt.get("remove") or []
    if not isinstance(add, list) or not isinstance(remove, list):
        raise ValueError("mark_tag.add and mark_tag.remove must be lists")
    if not add and not remove:
        raise ValueError("mark_tag.add and mark_tag.remove cannot both be empty")
    for t in add + remove:
        if not isinstance(t, str) or not t.strip():
            raise ValueError(f"invalid tag entry: {t!r}")
    # Normalize
    meta["mark_tag"] = {"add": add, "remove": remove}
    return meta


def _load_filter_dir(d: Path, source: str) -> FilterInfo | None:
    if not NAME_RE.match(d.name):
        return None
    if not _is_valid_filter_dir(d):
        return None
    try:
        with open(d / "meta.json") as f:
            meta = json.load(f)
        meta = _validate_meta(meta)
    except (json.JSONDecodeError, ValueError):
        return None
    return FilterInfo(name=d.name, dir=d, source=source, meta=meta)


def _discover_filters(cfg: Config) -> list[FilterInfo]:
    """Enumerate builtin + user filters; user overrides builtin on name."""
    by_name: dict[str, FilterInfo] = {}
    for source, base in (("builtin", BUILTIN_FILTERS_DIR), ("user", _user_filters_dir(cfg))):
        if not base.is_dir():
            continue
        for sub in sorted(base.iterdir()):
            if not sub.is_dir():
                continue
            info = _load_filter_dir(sub, source)
            if info is not None:
                by_name[info.name] = info
    return sorted(by_name.values(), key=lambda i: i.name)


def _resolve_filter(cfg: Config, name: str) -> FilterInfo:
    if not NAME_RE.match(name):
        raise click.ClickException(f"invalid filter name: {name!r}")
    user = _user_filters_dir(cfg) / name
    builtin = BUILTIN_FILTERS_DIR / name
    for d, source in ((user, "user"), (builtin, "builtin")):
        if d.is_dir():
            if not _is_valid_filter_dir(d):
                raise click.ClickException(
                    f"filter {name!r}: missing filter.py or meta.json"
                )
            try:
                with open(d / "meta.json") as f:
                    meta = json.load(f)
                meta = _validate_meta(meta)
            except (json.JSONDecodeError, ValueError) as e:
                raise click.ClickException(f"filter {name!r}: {e}")
            return FilterInfo(name=name, dir=d, source=source, meta=meta)
    raise click.ClickException(f"filter not found: {name}")


# ---------- run filter.py ----------

def _import_filter_module(info: FilterInfo):
    """Load filter.py as a fresh module via importlib (no subprocess)."""
    mod_name = f"_memorytalk_filter_{info.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(mod_name, info.dir / "filter.py")
    if spec is None or spec.loader is None:
        raise click.ClickException(
            f"filter {info.name!r}: cannot load {info.dir / 'filter.py'}"
        )
    module = importlib.util.module_from_spec(spec)
    # Re-import each time — filters are short-lived selectors; we don't
    # want stale module state between two `filter run` calls in the same
    # process (mostly relevant in tests).
    sys.modules.pop(mod_name, None)
    spec.loader.exec_module(module)
    return module


def _run_filter_py(info: FilterInfo, cfg: Config) -> list[str]:
    """Import filter.py and call its ``select(client)`` function.

    The ``client`` callable is a thin wrapper around ``cli/_http.api()``
    so filters share the CLI's transport (and any test-time monkeypatch
    of ``_make_client``). Filter authors get a single function-call
    signature instead of having to manage subprocess / HTTP themselves.
    """
    module = _import_filter_module(info)
    select = getattr(module, "select", None)
    if not callable(select):
        raise click.ClickException(
            f"filter {info.name!r}: filter.py must define a callable `select(client)`"
        )

    def client(method: str, path: str, *, json_body=None, params=None):
        return api(method, path, cfg, json_body=json_body, params=params)

    try:
        result = select(client)
    except Exception as e:  # noqa: BLE001 — surface filter author bugs as CLI errors
        raise click.ClickException(
            f"filter {info.name!r}: select() raised {type(e).__name__}: {e}"
        )

    if not isinstance(result, list):
        raise click.ClickException(
            f"filter {info.name!r}: select() must return list[str], got {type(result).__name__}"
        )
    out: list[str] = []
    for item in result:
        if not isinstance(item, str):
            raise click.ClickException(
                f"filter {info.name!r}: select() returned non-string item: {item!r}"
            )
        item = item.strip()
        if item:
            out.append(item)
    return out


# ---------- mark / unmark ----------

def _subject_route(subject_id: str) -> str | None:
    if subject_id.startswith("sess_"):
        return f"/v2/sessions/{subject_id}/tags"
    if subject_id.startswith("card_"):
        return f"/v2/cards/{subject_id}/tags"
    return None


def _tag_key(tag_str: str) -> str:
    """Extract the key portion (left of first ':') from a key[:value] tag string."""
    return tag_str.split(":", 1)[0].strip()


def _apply_one(
    cfg: Config, subject_id: str,
    add_tags: list[str], remove_tags: list[str],
) -> dict:
    """Apply add+remove tag ops to one subject. Returns a result dict suitable
    for both markdown and JSON rendering. Per-subject errors are caught and
    surfaced in the dict, never raised."""
    result: dict = {
        "subject_id": subject_id,
        "added": [],
        "removed": [],
        "errors": [],
    }
    path = _subject_route(subject_id)
    if path is None:
        result["errors"].append("invalid subject_id prefix (not sess_/card_)")
        return result

    if add_tags:
        try:
            api("POST", path, cfg, json_body={"tags": add_tags})
            result["added"] = list(add_tags)
        except ApiError as e:
            result["errors"].append(f"add: {extract_error_message(e.payload)}")

    if remove_tags:
        keys = [_tag_key(t) for t in remove_tags]
        keys = [k for k in keys if k]
        if keys:
            try:
                api("DELETE", path, cfg, params=[("key", k) for k in keys])
                result["removed"] = list(remove_tags)
            except ApiError as e:
                result["errors"].append(f"remove: {extract_error_message(e.payload)}")

    return result


def _find_subjects_with_tag_key(cfg: Config, key: str) -> list[str]:
    """Use /v2/search to find sessions + cards with the given tag key."""
    body = {"query": "", "where": f'tag = "{key}"'}
    try:
        resp = api("POST", "/v2/search", cfg, json_body=body)
    except ApiError:
        return []
    out: list[str] = []
    for r in (resp.get("sessions", {}).get("results") or []):
        out.append(r["session_id"])
    for r in (resp.get("cards", {}).get("results") or []):
        out.append(r["card_id"])
    return out


# ---------- Click commands ----------

@click.group("filter")
def filter_() -> None:
    """Viewfinder over subjects: list / run / mark / unmark."""


@filter_.command("list")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def filter_list(data_root: str | None, json_out: bool) -> None:
    """List installed filters (builtin + user)."""
    cfg = Config(data_root) if data_root else Config()
    filters = _discover_filters(cfg)
    if json_out:
        emit_json({"filters": [_filter_summary(f) for f in filters]})
        return
    emit_md(_fmt_filter_list(filters))


@filter_.command("run")
@click.argument("name")
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def filter_run(name: str, data_root: str | None, json_out: bool) -> None:
    """Run filter.py and display subject_ids in frame."""
    cfg = Config(data_root) if data_root else Config()
    info = _resolve_filter(cfg, name)
    subject_ids = _run_filter_py(info, cfg)
    if json_out:
        emit_json({"filter": info.name, "subject_ids": subject_ids})
        return
    emit_md(_fmt_run(info.name, subject_ids))


@filter_.command("mark")
@click.argument("name")
@click.argument("subject_ids", nargs=-1, required=True)
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def filter_mark(name: str, subject_ids: tuple[str, ...],
                data_root: str | None, json_out: bool) -> None:
    """Apply mark_tag ops (add/remove) to specific subject(s)."""
    cfg = Config(data_root) if data_root else Config()
    info = _resolve_filter(cfg, name)
    add = info.meta["mark_tag"]["add"]
    remove = info.meta["mark_tag"]["remove"]

    results = [_apply_one(cfg, sid, add, remove) for sid in subject_ids]
    _emit_apply_result(info.name, results, "mark", json_out)


@filter_.command("unmark")
@click.argument("name")
@click.argument("subject_ids", nargs=-1)
@click.option("--data-root", type=click.Path(), default=None)
@click.option("--json", "json_out", is_flag=True, default=False)
def filter_unmark(name: str, subject_ids: tuple[str, ...],
                  data_root: str | None, json_out: bool) -> None:
    """Reverse mark_tag ops. With no subject_ids, applies globally."""
    cfg = Config(data_root) if data_root else Config()
    info = _resolve_filter(cfg, name)
    add = info.meta["mark_tag"]["add"]
    remove = info.meta["mark_tag"]["remove"]

    if subject_ids:
        targets = list(subject_ids)
    else:
        # Global: find all subjects currently bearing any of `add`'s keys.
        # For `remove` list, we skip global re-add (over-tag risk; doc warns).
        seen: set[str] = set()
        for tag in add:
            key = _tag_key(tag)
            for sid in _find_subjects_with_tag_key(cfg, key):
                seen.add(sid)
        targets = sorted(seen)

    # Inverse: swap add and remove
    results = [_apply_one(cfg, sid, remove, add) for sid in targets]
    _emit_apply_result(info.name, results, "unmark", json_out)


# ---------- formatters ----------

def _filter_summary(info: FilterInfo) -> dict:
    return {
        "name": info.name,
        "source": info.source,
        "mark_tag": info.meta["mark_tag"],
    }


def _ops_label(add: list[str], remove: list[str]) -> str:
    bits: list[str] = []
    for t in add:
        bits.append(f"+`{t}`")
    for t in remove:
        bits.append(f"-`{t}`")
    return " ".join(bits) if bits else "—"


def _fmt_filter_list(filters: list[FilterInfo]) -> str:
    lines = [f"# filters ({len(filters)})", ""]
    if not filters:
        lines.append("*(none)*")
        return "\n".join(lines) + "\n"
    lines.append("| name | source | mark_tag |")
    lines.append("|---|---|---|")
    for f in filters:
        ops = _ops_label(f.meta["mark_tag"]["add"], f.meta["mark_tag"]["remove"])
        lines.append(f"| `{f.name}` | {f.source} | {ops} |")
    return "\n".join(lines) + "\n"


def _fmt_run(name: str, subject_ids: list[str]) -> str:
    lines = [f"# filter run `{name}` ({len(subject_ids)})", ""]
    if not subject_ids:
        lines.append("*(empty frame)*")
        return "\n".join(lines) + "\n"
    for sid in subject_ids:
        lines.append(f"- `{sid}`")
    return "\n".join(lines) + "\n"


def _fmt_apply(name: str, results: list[dict], action: str) -> str:
    lines = [f"# filter {action} `{name}` ({len(results)})", ""]
    if not results:
        lines.append("*(no subjects)*")
        return "\n".join(lines) + "\n"
    for r in results:
        ops: list[str] = []
        for t in r["added"]:
            ops.append(f"+`{t}`")
        for t in r["removed"]:
            ops.append(f"-`{t}`")
        suffix = " ".join(ops) if ops else "(noop)"
        line = f"- `{r['subject_id']}`: {suffix}"
        if r["errors"]:
            line += "  **errors:** " + "; ".join(r["errors"])
        lines.append(line)
    return "\n".join(lines) + "\n"


def _emit_apply_result(name: str, results: list[dict],
                       action: str, json_out: bool) -> None:
    if json_out:
        emit_json({"filter": name, "action": action, "applied": results})
    else:
        emit_md(_fmt_apply(name, results, action))
    # Exit nonzero only if all subjects had errors; partial failures still exit 0
    if results and all(r["errors"] for r in results):
        sys.exit(1)
