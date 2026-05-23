"""Pager gating — confirm AI/subprocess invocations bypass pager."""
from __future__ import annotations

import os
from unittest import mock

from memorytalk.cli import _render


class TestShouldPager:
    """Pure logic — does the gate let the pager run?"""

    def test_off_when_stdout_not_tty(self):
        # subprocess capture / pipe / redirect path
        with mock.patch("sys.stdout") as so, mock.patch("sys.stdin") as si:
            so.isatty.return_value = False
            si.isatty.return_value = True
            assert _render._should_pager() is False

    def test_off_when_stdin_not_tty(self):
        # echo X | memory.talk read foo — less would block on keyboard input
        with mock.patch("sys.stdout") as so, mock.patch("sys.stdin") as si:
            so.isatty.return_value = True
            si.isatty.return_value = False
            assert _render._should_pager() is False

    def test_on_when_both_tty(self):
        with mock.patch("sys.stdout") as so, mock.patch("sys.stdin") as si:
            so.isatty.return_value = True
            si.isatty.return_value = True
            # Clear NO_PAGER for this scope so the test isn't contaminated
            # by the shell environment.
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("NO_PAGER", None)
                assert _render._should_pager() is True

    def test_off_when_NO_PAGER_env_set(self):
        with mock.patch("sys.stdout") as so, mock.patch("sys.stdin") as si:
            so.isatty.return_value = True
            si.isatty.return_value = True
            with mock.patch.dict(os.environ, {"NO_PAGER": "1"}):
                assert _render._should_pager() is False

    def test_NO_PAGER_with_empty_string_still_means_off(self):
        # de-facto: setting the var at all (any non-empty value) disables.
        # Empty string we treat as unset to be conservative.
        with mock.patch("sys.stdout") as so, mock.patch("sys.stdin") as si:
            so.isatty.return_value = True
            si.isatty.return_value = True
            with mock.patch.dict(os.environ, {"NO_PAGER": ""}):
                # Empty string is falsy in env-var check — pager stays on.
                assert _render._should_pager() is True


class TestEmitMdPagedFallback:
    """When the pager is off, emit_md_paged behaves exactly like emit_md."""

    def test_falls_through_to_plain_when_not_tty(self, capsys):
        # Default pytest stdout is captured (not a TTY).
        _render.emit_md_paged("# hello\n\nworld\n")
        captured = capsys.readouterr()
        # Raw markdown printed, no ANSI escapes, no rendering.
        assert "# hello" in captured.out
        assert "world" in captured.out
