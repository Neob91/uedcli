+++
priority = "p2"
kind = "implement"
summary = "Adopt `EXEC <file>` batch driving for write-only editor sequences"
+++

# Adopt `EXEC <file>` batch driving for write-only editor sequences

Spike
PROVEN (`spikes/2026-07-18-exec-file-console-batch/results.md`, 8/8 probes live-confirmed;
regression `test_driver_integration.py::test_exec_file_runs_script_and_continues_past_errors`;
facts in `unrealed/commands.md` "`EXEC <file>`" + `quirks.md`): the console `EXEC Z:\work\<file>`
verb runs a command script — in order, LF or CRLF, continue-on-error, nested OK, **executes
THROUGH the GC `xmessage` dialog** that stalls typed commands, ~6× less drive overhead (6 cmds:
7.05s typed vs 1.20s scripted). No open design question — the adoption shape is fixed by the
spike's "Adoption implications": batch the **write-only** materialize runs (`OBJ LOAD`s → import →
`MAP REBUILD` → `LIGHT APPLY` → `MAP SAVE`) into one `EXEC` submission with a **completion-marker
last line** (a final `MAP EXPORT FILE=Z:\work\<uuid>-done.t3d`, host polls for it); crash detection
stays liveness-based; **read-back steps** (`EDIT COPY`, export-and-parse) keep per-command
round-trips. **What the plan must sequence/scope:** which `driver.py`/`writes.py`/`materialize.py`
seams batch first (the contiguous write-only spans), the marker-poll + liveness-during-poll loop,
and per-`EXEC` error/GPF handling (no per-command feedback). **Composes with — does not block, and
is not blocked by — the warm-editor spec** (`specs/2026-07-18-warm-editor-materialize.md` §10): a
per-build win on BOTH warm and ephemeral paths; the completion poll is `wine_ctl`-based so it still
refreshes the §4.5 idle marker. Andrzej-initiated. (Triaged from inbox 2026-07-19.)
