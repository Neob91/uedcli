"""The single import point for the compiled `uedcli_native` extension, gating every caller
against a STALE build.

`bin/uedcli` (via `bin/_venv.sh::ensure_native_ext`) hashes `uedcli-native/`'s Rust sources on
every invocation and exports `UEDCLI_NATIVE_EXT_FRESH=1` only when the installed wheel's content
matches that hash (freshly rebuilt, or already current) -- `"0"` whenever a rebuild was needed but
could not be produced (Docker unavailable, a build failure, host resource contention). Without
this gate, a bare `import uedcli_native` would silently keep running whatever was last
successfully built, possibly stale by any number of commits, with no signal at the point of use --
exactly the kind of silent partial/wrong result `dev/docs/direction/conventions.md` forbids
elsewhere in this CLI.

A raw script that bypasses `bin/uedcli` (doesn't set the env var at all -- e.g. a dev script
launched with a bare `.venv/bin/python`, or `pytest` run directly) is NOT gated: only `"0"`
(confirmed stale) blocks; an unset/unknown state does not. Ad-hoc scripts and test runs that
manage their own build lifecycle keep today's behavior. The guarantee is scoped to `bin/uedcli`
specifically (owner ruling, 2026-09-11).

`NativeExtensionStaleError` subclasses `ImportError` on purpose: every existing call site already
does `import uedcli_native` and, where it cares, catches `ImportError` to raise its own
domain-specific "not built" error (`NativePreviewError`, `NativeBuildError`, `PathPlaceError`,
...). Subclassing means those call sites catch a stale extension the same way, with zero changes
to their own error text."""
import os


class NativeExtensionStaleError(ImportError):
    """`uedcli_native` is installed but does not match `uedcli-native/`'s current Rust source, and
    `bin/uedcli` could not rebuild it (Docker unavailable, or the build failed) -- refusing to run
    possibly-wrong compiled code rather than silently using the stale build."""


def import_native():
    """Import and return the `uedcli_native` module, refusing a confirmed-stale build. See the
    module docstring for the `UEDCLI_NATIVE_EXT_FRESH` contract."""
    if os.environ.get("UEDCLI_NATIVE_EXT_FRESH") == "0":
        raise NativeExtensionStaleError(
            "uedcli_native is stale (the installed build does not match uedcli-native/'s current "
            "source) and bin/uedcli could not rebuild it -- refusing to run possibly-wrong "
            "compiled code. See the 'uedcli: ...' message above; fix the build (or Docker) and "
            "retry.")
    import uedcli_native
    return uedcli_native
