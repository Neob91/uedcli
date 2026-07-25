# 2026-07-14 — Does `[Core.System] Paths` accept a middle-directory wildcard?

**Question (Andrzej: "prefer the simplification, but verify it"):** can the asset-wiring cutover craft
a few `Paths=/resources/*/*.<ext>` lines (a `*` in the DIRECTORY component) instead of one
`Paths=/resources/<n>/*.<ext>` per mounted dir × ext?

## Outcome — INCONCLUSIVE from a standalone probe; ship the proven per-dir form

The middle-dir wildcard could **not be verified** with a standalone editor probe, for methodology
reasons, NOT because it was shown to fail:

- `OBJ LOAD PACKAGE=<name>` (name only) is **not a reliable probe of `[Core.System] Paths`
  resolution** — it appears not to trigger the Paths file-search the way `MAP LOAD`/demand-load does.
  Both the wildcard AND the **known-good per-dir** form (`/resources/A/*.utx`) read as "NOT RESOLVED"
  with it, so the probe is uninformative, not the wildcard.
- `OBJ LIST CLASS=Texture NAME=grey_stone_tile` (the positive detector) also mis-fired — the same
  package listed fine UNFILTERED right after an explicit `OBJ LOAD FILE`, so the `NAME=` filter, not
  resolution, was the false negative.

**Decision:** the per-dir-per-ext form (`Paths=/resources/<n>/*.<ext>`) is **proven in production** —
`uned/entrypoint.sh` already ships exactly this for `/deusex/*`, and every materialize this session
found its textures through it. So the cutover ships on per-dir-per-ext (spec §3 floor). The wildcard
is a *fewer-ini-lines* optimisation whose only correct verification is **end-to-end**: a real
`level materialize` with wildcard-only `Paths` and no explicit `OBJ LOAD FILE` for the content — that
belongs in the build's integration test, not a synthetic probe. Deferred there.

## Two REAL, verified build findings (the spike's actual value)

Both are load-bearing for the cutover's pre-launch ini mechanism (spec §5):

1. **The crafted ini MUST be written byte-exact (CRLF preserved).** `Path.read_text()` applies
   universal-newlines and turns the ini's CRLF into LF; wine's ini parser is CRLF-sensitive and
   **GPFs at boot** on an LF ini → no editor window → readiness timeout. (First run: all four variants
   timed out purely from this; fixed by `read_bytes`/`write_bytes`.) `container_assets`/`editor.py`
   must craft the ini in bytes.
2. **`unrealtournament.ini` cannot be bind-mounted while anything `sed -i`-edits it.** The entrypoint's
   `/deusex` Paths block does `sed -i /opt/UED22/unrealtournament.ini`; `sed -i`'s rename-over fails on
   a single-file bind mount → the entrypoint dies → no boot. (Confirmed: a plain editor boots; adding
   the ini bind-mount with `/deusex` present does not; pointing the entrypoint's deusex dir at a
   nonexistent path — i.e. simulating the block's removal — makes it boot.) So the entrypoint's Paths
   block MUST be deleted (spec §7) BEFORE the pre-launch ini bind-mount works — they are mutually
   exclusive, and the cutover already removes it.

## Harness

`probe.py` — boots a fresh ephemeral editor per variant with a byte-exact crafted
`unrealtournament.ini` bind-mounted pre-launch (`UED_DEUSEX_ASSETS_DIR` pointed at nothing to skip the
entrypoint sed), a package at `/resources/A/`, and probes `OBJ LOAD PACKAGE` + `OBJ LIST`. Kept for the
two findings above and as the seed for the end-to-end wildcard check. `_scratch/wc_final.py` /
`pd_final.py` were the single-boot A/B (wildcard vs per-dir) that showed the probe itself is
inconclusive.
