"""Render ``${VAR}`` env-var references in strings via string.Template.

Strict (``substitute``, not ``safe_substitute``) — a missing env var
raises ``KeyError``; callers turn that into a clear error rather than
silently sending an empty value. Strings without any ``$`` pass through
untouched. Embed a literal ``$`` as ``$$``.

Used at config-load time (``config._load_settings``) so the rest of the
codebase treats ``Settings.embedding.auth_key`` as a literal API key,
regardless of whether settings.json stored ``${QWEN_KEY}`` or the raw
key. Also used by the wizard's pre-write probe (``validate_embedder``)
because that path constructs ``Settings`` directly from the user's input
dict, bypassing disk-load.
"""
from __future__ import annotations
import os
from string import Template


def render_env_template(s: str) -> str:
    return Template(s).substitute(os.environ)


def render_env_in_obj(obj):
    """Recursively render ``${VAR}`` in every string within ``obj``,
    mutating in place. Nested dicts and lists are traversed; non-string
    leaves are left untouched. Strict — a missing env var raises
    ``KeyError``.

    Used by ``Config._load_settings`` so any field that happens to hold
    a ``${VAR}`` reference gets rendered at the disk-load boundary,
    without per-field plumbing.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                obj[k] = render_env_template(v)
            elif isinstance(v, (dict, list)):
                render_env_in_obj(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = render_env_template(v)
            elif isinstance(v, (dict, list)):
                render_env_in_obj(v)
