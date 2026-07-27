+++
priority = "p?"
kind = "unknown"
summary = "#10 build review — round 1 only, round 2 SKIPPED at Andrzej's explicit instruction (2026-07-25)"
+++

# #10 build review — round 1 only, round 2 SKIPPED at Andrzej's explicit instruction (2026-07-25)

Round 1 ran the full build tier (2 Opus + 1 Haiku, cold, given `CLAUDE.md` + the
§10 spec text, no priming). Resolving it **did change the artifact**, so the gate's own rule would
have fired a round 2 (1 Opus); Andrzej directed in-session that this item stop after one round.
Recorded here rather than only in chat, per the "reason goes on the board" rule — the gate text in
`CLAUDE.md` is unchanged and this is a one-item exception, not a precedent. **Fixed** in round 1:
PNG round-trip removed from the breakdown path (it now returns a Pillow `Image`); `--out` naming an
existing directory / `""` / `.` now exits 2 instead of silently writing a sibling file; NaN/inf
dimensions now rejected by the guard (`<= 0` waves NaN through); the enforcement test widened from
"required float flags" to "every float flag, minus an explicit angle allow-list" (a dimension with
a DEFAULT was invisible to it) and the three places that overstated it corrected; `README.md`'s
`--png` quickstart and its retired dev-container claim; five stale test names/comments; dead
`single=`/`zoom=`/`zoom_region=`/`format=` kwargs in two test files; two `board/inbox/` items this
change completed or obsoleted; the 2026-07-22 ledger claim that the annotation internals "stay
label-named" (superseded, not reworded). **Logged** to `board/inbox/`: two ANDRZEJ-decide items (guard
layer placement; the partial 10.3 rename), the pre-existing `test_zoom_does_not_highlight`
weakness, and the red intermediate commit. The Haiku reviewer returned no findings but misreported
the suite counts and cited spec line numbers as if read from the file — treated as low-confidence.
