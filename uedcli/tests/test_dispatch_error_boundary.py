"""Slice 1 characterization of `dispatch.dispatch()`'s process-wide error guard.

The guard is the ordered `try/except` chain that turns every expected failure into a clean exit
with a specific stderr message, never a traceback. The reorg keeps this chain central and its arm
order intact, so this test pins one stderr/exit regression for EVERY exception class it catches,
plus the `TimeoutError`-before-`OSError` precedence that keeps editor timeouts their own message.

Coverage is driven by patching the internal `_dispatch` seam to raise a representative instance:
that isolates the guard's translation from any handler's internals, which is exactly what must be
preserved. A handful of genuine end-to-end triggers follow, proving real flows still reach the
matching arm.
"""
from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stderr

import pytest

from uedcli import config, schema_cache
from uedcli.cli import errors
from uedcli.cli import dispatch as D
from uedcli.classindex import ClassRefError
from uedcli.driver import DriverError
from uedcli.editor import EditorNotReadyError
from uedcli.geometry import GeometryError
from uedcli.model import CoordinateError
from uedcli.uprops import SchemaError


def _raiser(exc):
    def _inner(_args):
        raise exc
    return _inner


# (label, exception factory, expected exit code, expected stderr substring)
GUARD_CASES = [
    ("selection_exit",   lambda: D.CommandError("boom-sel"),                 2, "boom-sel"),
    ("project_error",    lambda: D.ProjectError("boom-proj"),                 2, "boom-proj"),
    ("level_selection",  lambda: errors.LevelSelectionError("boom-lvl"), 2, "boom-lvl"),
    ("config_error",     lambda: config.ConfigError("boom-cfg"),               2, "boom-cfg"),
    ("coordinate",       lambda: CoordinateError("boom-coord"),                2, "invalid coordinate: boom-coord"),
    ("geometry",         lambda: GeometryError("boom-geo"),                    2, "invalid brush geometry: boom-geo"),
    ("driver",           lambda: DriverError("boom-drv"),                      2, "editor error: boom-drv"),
    ("timeout",          lambda: TimeoutError("boom-to"),                      2, "editor error: boom-to"),
    ("editor_not_ready", lambda: EditorNotReadyError("boom-enr"),              2, "editor error: boom-enr"),
    ("class_ref",        lambda: ClassRefError("boom-cref"),                   2, "boom-cref"),
    ("schema",           lambda: SchemaError("boom-schema"),                   2, "schema error: boom-schema"),
    ("cache_write",      lambda: schema_cache.CacheWriteError("boom-cache"),   2, "boom-cache"),
    ("oserror",          lambda: OSError("boom-os"),                           2, "filesystem error: boom-os"),
]


@pytest.mark.parametrize("label,factory,exit_code,substr",
                         GUARD_CASES, ids=[c[0] for c in GUARD_CASES])
def test_guard_translates_each_exception_class(monkeypatch, capsys, label, factory, exit_code, substr):
    monkeypatch.setattr(D, "_dispatch", _raiser(factory()))
    rc = D.dispatch(argparse.Namespace())
    cap = capsys.readouterr()
    assert rc == exit_code
    assert substr in cap.err
    assert "Traceback" not in cap.err


def test_timeout_arm_precedes_oserror_arm(monkeypatch, capsys):
    """`TimeoutError` (and its `EditorNotReadyError` subclass) subclass `OSError`; the guard lists
    the editor arm first, so an editor timeout keeps `editor error:` rather than falling through to
    the filesystem `OSError` backstop. Pins that precedence, not just the two messages."""
    monkeypatch.setattr(D, "_dispatch", _raiser(EditorNotReadyError("startup died")))
    assert D.dispatch(argparse.Namespace()) == 2
    assert "editor error: startup died" in capsys.readouterr().err

    monkeypatch.setattr(D, "_dispatch", _raiser(OSError("no such dir")))
    assert D.dispatch(argparse.Namespace()) == 2
    assert "filesystem error: no such dir" in capsys.readouterr().err


def test_broken_pipe_is_a_silent_exit_zero(monkeypatch):
    """A gone stdout consumer (`uedcli … | head`) exits 0 with no error, and the guard detaches
    stdout so interpreter shutdown can't re-raise. Restore `sys.stdout` afterwards so the detach
    can't leak into other tests."""
    saved = sys.stdout
    monkeypatch.setattr(D, "_dispatch", _raiser(BrokenPipeError()))
    try:
        rc = D.dispatch(argparse.Namespace())
        assert sys.stdout is not saved            # the guard replaced it with a devnull sink
    finally:
        sys.stdout = saved
    assert rc == 0


# --- genuine end-to-end triggers: real flows still reach the matching arm ---

def _show_ns(**kw):
    base = dict(cmd="actor", sub="show", name=["X"], project=None, tree=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_missing_project_reaches_project_arm(capsys):
    rc = D.dispatch(_show_ns(project=None))
    err = capsys.readouterr().err
    assert rc == 2 and "not in a uedcli project" in err and "Traceback" not in err


def test_bad_tree_reaches_selection_arm(tmp_path, capsys):
    (tmp_path / "uedcli.toml").write_text('game = "deusex"\n')
    rc = D.dispatch(_show_ns(project=str(tmp_path), tree="bogus"))
    err = capsys.readouterr().err
    assert rc == 2 and "--tree must be KIND/NAME" in err and "Traceback" not in err


def test_bare_name_project_reaches_config_arm(capsys):
    rc = D.dispatch(_show_ns(project="no-such-registered-name"))
    err = capsys.readouterr().err
    assert rc == 2 and "name-based project lookup" in err and "Traceback" not in err
