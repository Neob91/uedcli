"""`uedcli.native_ext.import_native` — the `UEDCLI_NATIVE_EXT_FRESH` gate every `uedcli_native`
call site now goes through (`bin/_venv.sh::ensure_native_ext` sets it). Hermetic: never depends on
the real compiled extension being installed."""
import sys
import types

import pytest

from uedcli.native_ext import NativeExtensionStaleError, import_native


def test_stale_env_var_raises_before_importing_the_real_module(monkeypatch):
    """`UEDCLI_NATIVE_EXT_FRESH=0` is a hard stop, regardless of whether `uedcli_native` is even
    installed -- the check must happen BEFORE the underlying import is attempted."""
    monkeypatch.setenv("UEDCLI_NATIVE_EXT_FRESH", "0")
    monkeypatch.delitem(sys.modules, "uedcli_native", raising=False)
    with pytest.raises(NativeExtensionStaleError, match="stale"):
        import_native()


def test_stale_error_is_an_import_error():
    """Every existing `uedcli_native` call site already does `except ImportError:` to raise its
    own domain-specific "not built" error -- subclassing means a stale build is caught there too,
    with zero changes to that error text."""
    assert issubclass(NativeExtensionStaleError, ImportError)


def test_fresh_env_var_imports_the_real_module(monkeypatch):
    monkeypatch.setenv("UEDCLI_NATIVE_EXT_FRESH", "1")
    fake = types.ModuleType("uedcli_native")
    monkeypatch.setitem(sys.modules, "uedcli_native", fake)
    assert import_native() is fake


def test_unset_env_var_does_not_block(monkeypatch):
    """A raw script that bypasses `bin/uedcli` (never sets the var at all) keeps today's
    behavior -- only a CONFIRMED-stale ("0") build blocks, not an unknown state."""
    monkeypatch.delenv("UEDCLI_NATIVE_EXT_FRESH", raising=False)
    fake = types.ModuleType("uedcli_native")
    monkeypatch.setitem(sys.modules, "uedcli_native", fake)
    assert import_native() is fake


def test_a_previously_bare_call_site_raises_its_own_domain_error_not_a_traceback(monkeypatch):
    """`brushcsg.merge` (a common, everyday verb -- `brush merge`/`actor merge`) called
    `import_native()` with no surrounding `try/except` before this change, so a stale extension
    would have propagated `NativeExtensionStaleError` straight out as an unhandled exception. It
    now converts to `BrushCsgError`, matching the file's existing "never let a Python exception
    reach the user" convention -- pinned end-to-end, not just at `import_native()` in isolation."""
    from uedcli import brushcsg
    monkeypatch.setenv("UEDCLI_NATIVE_EXT_FRESH", "0")
    monkeypatch.delitem(sys.modules, "uedcli_native", raising=False)
    # The extension import is the FIRST thing `merge` does, before touching `actors` at all -- an
    # empty list is enough to reach it without needing real brush fixtures.
    with pytest.raises(brushcsg.BrushCsgError, match="not usable"):
        brushcsg.merge([], deintersect=False)
