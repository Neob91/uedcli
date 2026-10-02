+++
priority = "p2"
kind = "debug"
summary = "sound list leaks BrokenPipeError traceback when piped to head"
+++

# sound list leaks BrokenPipeError traceback when piped to head

`sound list | head` prints `BrokenPipeError: [Errno 32] Broken pipe` to stderr when the
reader closes the pipe early. Violates `CLAUDE.md` "never let a Python exception reach the
user". Reproduced 5/5.

    $ bin/uedcli sound list | head -2
    ...
    BrokenPipeError: [Errno 32] Broken pipe

Scope: audio arm only. `texture list`, `class list`, `music list` piped to `head` are clean
(`music` has 0 objects here, so it never fills the pipe). So it's the sound `list` writer,
not shared list code.

Fix: the standard SIGPIPE / BrokenPipe guard on the stdout writer (catch and exit 0, or
restore SIG_DFL for SIGPIPE at startup). Add a regression test piping `sound list` into a
1-line reader and asserting no traceback on stderr.
