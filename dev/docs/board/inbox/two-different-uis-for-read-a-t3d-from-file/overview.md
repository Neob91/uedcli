+++
priority = "p3"
kind = "owner-question"
summary = "Two different UIs for \"read a T3D from file-or-stdin\""
+++

# Two different UIs for "read a T3D from file-or-stdin"

p3. `actor add`
  takes a **positional** arg (`-` = stdin, else a path), while `stash capture` takes **flags**
  `--from-t3d PATH` / `--from-stdin`. So `actor add` can't use `--from-t3d` and `stash capture`
  can't take a positional `-`. The error handling is now unified (`_read_t3d_input`), but the surface
  is split. Defensible (stash capture's default source is the selected level, so it needs explicit
  override flags), but worth deciding whether to also accept `stash capture -` for symmetry.
  (Surfaced by a cold reviewer during the exception-safety hardening, 2026-07-12.)

<!-- ═══════════════════════════════════════════════════════════════════════════════
     DOGFOODING FINDINGS (2026-07-12) — surfaced building, previewing, and expanding
     a castle end-to-end (brush build → actor add → doctor → level preview → texture →
     materialize → concentric-bailey expansion). Grouped by subsystem; deduplicated;
     CRITICAL/HIGH severity called out inline. See decisions.md 2026-07-12 (preview).
     ═══════════════════════════════════════════════════════════════════════════════ -->
