+++
priority = "p3"
kind = "debug"
summary = "A doubly-signed poly index (`Wall:--3`) escapes as a raw Python message that names nothing"
+++

# A doubly-signed poly index (`Wall:--3`) escapes as a raw Python message that names nothing

`surface.resolve_polys` gates each index with `part.lstrip("-").isdigit()`, which strips
*every* leading `-`, so `--3` passes the guard and reaches `int()`:

```
$ uedcli brush poly rotate ROOM:--3 --by 16384
rc=2  invalid literal for int() with base 10: '--3'
```

It is a clean exit 2 — `dispatch` catches `ValueError` — so no traceback reaches the user, which is
why this is `p3` and not higher. But the message names neither the brush nor the verb and does not
read as a uedcli error at all, unlike every neighbouring case on the same input:

```
ROOM:+3   →  'ROOM': bad poly index '+3' (expected an integer)
ROOM:-3   →  'ROOM': poly index -3 out of range (brush has 6 polys)
ROOM:x    →  'ROOM': bad poly index 'x' (expected an integer)
```

The fix is to make the guard reject a second sign (e.g. strip at most one leading `-`, or match
against a signed-integer pattern) so `--3` lands on the existing `bad poly index` message. Every
`BRUSH:SELECTOR` verb inherits it: `brush poly list|find|set|pan|rotate|scale|align`.

**Deferred deliberately, not missed:** `resolve_polys` is **byte-identical to master's** (verified
by diffing the function against `master:uedcli/surface.py`), so this is pre-existing and out of
scope for the per-surface step-1 change — that change only added three more verbs through which the
same pre-existing guard is reachable. Found by the step-1 build review, 2026-07-27.
