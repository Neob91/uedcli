+++
priority = "p2"
kind = "implement"
summary = "GUI sessions: per-tab, durable, own staged edits + build, no auto-expiry"
+++

# Persistent GUI editing sessions

`uedcli serve`'s GUI currently has no session concept: staged edits are keyed only by level (so every
browser tab pointed at the same level shares one staged set), an accidental refresh only survives
because staging writes through immediately (not because of any session), and the server holds exactly
one level "hot" in memory at a time (`PUT /api/level` swaps it for the whole process).

This introduces durable, per-tab sessions: each gets its own id, its own staged edits, its own
independently-solved geometry/lighting build (deduped against a shared content-hash cache), and
survives both a browser refresh and a server restart. No auto-expiry — a session lives until
explicitly closed. See `spec.md`.
