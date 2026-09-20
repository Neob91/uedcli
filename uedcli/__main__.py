import sys
from .cli.main import main

if __name__ == "__main__":
    # A Nuitka --mode=standalone compile doesn't replicate CPython's own PEP 538/540 UTF-8
    # coercion under a C/POSIX locale (no LANG/LC_ALL set, e.g. a minimal container) -- a non-ASCII
    # help/error string can crash with UnicodeEncodeError there even though the same source runs
    # fine under plain CPython in the identical environment. Force UTF-8 unconditionally to match
    # what CPython already guarantees on its own; a no-op when stdout/stderr are already UTF-8.
    # This whole block is a best-effort environment adaptation, not part of the CLI's own logic --
    # dispatch()'s exception handling (CLAUDE.md: no bare Python exception reaches the user) starts
    # only once main() is called, so a failure here (already-closed stream, one swapped for
    # something without reconfigure()) must not itself raise; falling back to the original,
    # pre-existing behavior is exactly correct for a fix this narrowly scoped.
    # errors="replace": reconfigure() resets the stream's error handler to TextIOWrapper's
    # "strict" default, even though CPython's own stdio starts with "surrogateescape" -- silently
    # narrowing this fix to reintroduce the same UnicodeEncodeError class for any surrogate-escaped
    # string (e.g. a non-UTF-8 filename recovered via os.fsdecode). Confirmed empirically:
    # `sys.stdout.errors` goes from "surrogateescape" to "strict" under a bare `encoding="utf-8"`
    # reconfigure. Matches the tested fix in dev/docs/spikes/2026-09-19-nuitka-standalone-native-
    # ext/spike.md Addendum 2.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
