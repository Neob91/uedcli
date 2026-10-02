+++
priority = "p3"
kind = "debug"
summary = "Fixed — resolve_polys now rejects a second leading sign instead of passing `--3` raw to int()"
+++

# A doubly-signed poly index (`Wall:--3`) escapes as a raw Python message that names nothing

Fixed in `uedcli/surface.py:resolve_polys()` — the guard is now `re.fullmatch(r"-?\d+", part)`
instead of `part.lstrip("-").isdigit()`, so `--3` lands on the existing `bad poly index` message.
