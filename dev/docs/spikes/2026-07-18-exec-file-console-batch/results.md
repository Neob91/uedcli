# Spike: `EXEC <file>` — batching editor console commands through a command-script file

**Date:** 2026-07-18 (all probes live-confirmed against a fresh ephemeral `dx-lum-uned` editor).
**Question (Andrzej):** instead of typing each console command into UnrealEd's Command box one at
a time, should uedctl write a command file and submit a single `EXEC <filename>` — and would that
be safer?
**Answer: YES — `EXEC` works, is ~6× faster per command on drive overhead, executes THROUGH the
GC blocking dialog that stalls the typed console, and shrinks the fragile X11-typing surface to
one short constant-shaped line.** Details + caveats below. Harness:
[`harness/exec_file_probe.sh`](harness/exec_file_probe.sh) (re-runs every probe against a named
container). Regression: `uedctl/tests/test_driver_integration.py::test_exec_file_runs_script_and_
continues_past_errors` (integration-marked).

## Why this was worth asking

Today every console command is delivered by `wine_ctl.py exec` as a full X11 pantomime: focus the
editor window, click into the bottom Command box, clear it (End, Shift+Home, Delete), `xdotool
type` the line character-by-character, press Return, settle 0.3s, scan for a crash dialog
(`uned/wine_ctl.py cmd_exec`). Each command is a separate `docker exec` + focus dance — each one
a chance for a stolen focus, a blocking dialog, or typing corruption, and the GC "Cleaning up..."
`xmessage` dialog (fires on nearly every `MAP NEW`/`IMPORTADD`/`REBUILD`, never auto-closes
headless) blocks every LATER submission until dismissed (`unrealed/quirks.md` Stability).
`EXEC <file>` was catalogued in `unrealed/commands.md` only as 📖 (present in the Engine.dll
string table, semantics unverified).

## Probes and findings (all ✅ live 2026-07-18)

1. **`EXEC Z:\work\cmds.txt` runs a command script.** A 3-line file of `MAP EXPORT FILE=...`
   commands, submitted as one typed `EXEC` line → all three exports written, in order.
   `Editor.log` echoes `Execing Z:\work\cmds.txt` (and a
   `FactoryCreateText: TextBuffer with TextBufferFactory` line — the file is imported as a
   TextBuffer, then executed line by line).
2. **A relative filename resolves against the System dir (`/opt/UED22`)**, NOT the process CWD or
   `/work`: with `relprobe.txt` present in BOTH `/opt/UED22` and `/work`, `EXEC relprobe.txt` ran
   the System-dir one. Absolute `Z:\...` paths work and are what uedctl should use (no ambiguity,
   `/work` is the container-scratch convention).
3. **Errors do NOT abort the script.** A file containing a bogus verb (`TOTALLYBOGUSVERB FOO=1`)
   and a failing `OBJ LOAD FILE=<missing>` between two exports → both exports still ran, editor
   alive. Same continue-on-unrecognized behavior as the typed console. Corollary: `EXEC` gives
   NO per-command error feedback — error detection stays what it is today (observable effects +
   log scrapes + liveness polls).
4. **THE BIG ONE — the GC `xmessage` dialog does NOT stall script execution.** A script of
   `MAP NEW` → `MAP EXPORT` → `BRUSH RESET` → `MAP EXPORT`: the GC dialog popped (visible in
   `wmctrl -l`) and BOTH post-`MAP NEW` commands still executed while it was up (exports present,
   sized for the post-reset level — proving order too). The dialog blocks the Command-*box UI
   input path*, not the engine's internal exec loop. A typed-console drive stalls there until
   dismissed; a script sails through, and the dialog needs dismissing only before the NEXT typed
   submission. Dismissal afterwards works exactly as before (`dismiss_blocking_dialog`).
5. **Line endings: LF and CRLF both work.** (The CRLF-only trap is the *ini* parser, not the
   TextBuffer import.)
6. **Nested `EXEC` works** (a script `EXEC`ing another script, then continuing).
7. **A garbage `MAP IMPORTADD` mid-script neither stalls nor kills it** — silently tolerated,
   following commands ran. (NOTE: this shows junk *import* is silent; it does not prove a true
   MODAL win32 dialog can never stall a script — the known headless blocker, the GC `xmessage`,
   demonstrably doesn't, and a Critical Error GPF box is a crash regardless.)
8. **Timing: 6 commands typed = 7.05s; the same 6 as one `EXEC` script = 1.20s** including the
   host-side file write and the completion poll (~6× on pure drive overhead; per-command cost is
   dominated by the focus/type/settle pantomime, which the script pays once).

## Adoption implications (for the editor-driving verbs — materialize etc.)

- **Completion detection = a marker as the LAST script line** (e.g. a final
  `MAP EXPORT FILE=Z:\work\<uuid>-done.t3d`; poll for the file). The typed `EXEC` submission
  returns immediately — nothing about the script's progress comes back through it.
- **Crash detection stays liveness-based:** `wine_ctl`'s post-Return crash-dialog scan covers
  only the `EXEC` submission; a GPF mid-script surfaces via the existing liveness/status polls
  (and the completion marker never appearing).
- **Interleaved reads keep their current shape:** commands whose OUTPUT the host consumes
  mid-sequence (`EDIT COPY` → clipboard, readback-and-parse steps) still need per-command
  round-trips; the win is for write-only runs (`OBJ LOAD`s → `MAP IMPORTADD`/`PASTE` → `MAP
  REBUILD` → `LIGHT APPLY` → `MAP SAVE`), which is most of a materialize drive.
- **Warm-editor interplay** (`specs/2026-07-18-warm-editor-materialize.md`): fewer `wine_ctl`
  invocations = fewer idle-marker touches, but the completion-poll loop IS `wine_ctl`/exec-based
  and refreshes the marker throughout — no watchdog conflict.

## Untested / out of scope

- Paths containing SPACES in script lines (no space-path exists in the container conventions;
  quote behavior unprobed).
- Very long lines (>~200 chars) inside a script file; very large scripts (hundreds of lines).
  Materialize-scale scripts (~10–40 lines) are proven by the probes.
- Comment syntax (moot: unrecognized lines are ignored, finding 3 — but don't rely on `;`/`//`
  being non-verbs).
- Whether a true modal win32 error dialog (not the async `xmessage`) can stall a script
  (finding 7's note).
