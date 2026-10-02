+++
priority = "p1"
kind = "debug"
summary = "build_ued_lit_golden.py: _wait_idle Driver/str mismatch breaks every fresh golden build"
+++

# build_ued_lit_golden.py: _wait_idle Driver/str mismatch breaks every fresh golden build

Fixed 2026-09-02: `build_ued_lit_golden.py`'s 5 `_wait_idle` call sites now pass the `Driver`
instance (`ed`) instead of the bare container-name string, matching `build_ued_golden.py`'s own
fixed sites. Live-verified on `DX.dx` — `obj-load` (the crashing call) completes with no
`AttributeError`. Detail: `dev/docs/native-materialize-findings.md`, 2026-09-02 entry.
