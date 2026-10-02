# Native materialize parity report — canonical entry point

Not a one-off investigation: this is a **permanent developer tool** for the native-materialize
effort, requested by the owner to end a real friction this session — dozens of duplicated,
per-level, per-dimension bespoke scripts (`regression_gate.py`, `breadth_gate.py`,
`light_spotcheck_unatco.py`, `light_spotcheck_wanchai.py`, …) and a duplicate-effort incident where
two agents independently re-ran the same expensive lighting sweep because there was no single
"is this level at full parity yet" answer. Lives here (a dated `spikes/` slug, per the project's
existing convention for a committed, permanent harness directory) rather than a new top-level
`dev/docs/` tree, to avoid inventing a second taxonomy for the same "committed, reusable script"
concept `dev/docs/rules/spikes.md` already covers.

## What it is

`harness/parity_report.py <path/to/OG-level.dx> [--json]` — one script, one verdict:
**FULL PARITY: YES/NO**. YES only if every geometry count (nodes/surfs/leaves/verts/points/vectors)
is byte-identical AND every `LightMap` record is byte-identical — stricter than `breadth_gate.py`'s
"EXACT" label, which only checks node/surf/leaf and ignores a verts/points/vectors delta.

- `harness/parity_lib.py` — pure logic: content hashing, the `/tmp` cache layout, geometry/lighting
  delta math, the FULL PARITY verdict, text/JSON report formatting. Unit tested offline
  (`harness/test_parity_lib.py`, 21 cases) — no docker, no editor, no `uedcli` import.
- `harness/parity_pipeline.py` — the editor-driving glue: extracts a T3D trunk from the input `.dx`
  (subprocess to `2026-07-15-native-materialize/harness/ingest_dx_trunk.py`, UCC batchexport, no
  live editor) and self-builds the lit golden (subprocess to
  `2026-08-27-native-light-apply-parity/harness/build_ued_lit_golden.py`: `MAP NEW` -> `EDIT PASTE`
  -> `MAP REBUILD` -> `LIGHT APPLY` -> `MAP SAVE`) — never `MAP LOAD` on the shipped original (see
  `native-materialize-findings.md`, "Golden .dx provenance — CONFIRMED, closed"). Not unit tested
  (needs docker + Wine); proven by the live runs below.
- `harness/parity_compare.py` — extracts geometry counts (native `build_geometry_bspcsg` vs the
  parsed golden `Model`, same read path as `regression_gate.py`/`breadth_gate.py`) and the lighting
  summary (native's own lit build via `build_world_model`+`gather_lights`+`assemble_unbuilt`,
  compared record-by-record via `lightparity.py`'s own helpers — same path
  `light_spotcheck_unatco.py`/`light_spotcheck_wanchai.py` use).

## Design decisions

**Cache layout is split across two roots, for a real infra reason, not a style choice.** The task
spec says cache the self-built golden under `/tmp/uedcli-parity-cache/<hash>/` — that's exactly
where `golden.dx` + `meta.json` + build logs live. But the extracted T3D trunk (needed on every run,
hit or miss, since native always builds fresh from it) lives under the REPO TREE instead
(`_scratch/uedcli-parity-cache/<hash>/trunk/`), because `dev/docs/parallel-editors.md` ("Isolation
requirements") documents a real Docker trap: `ephemeral_build_container` bind-mounts a crafted ini
under the trunk's own `.uedcli/tmp/`, and a sandboxed shell's `/tmp` is private to the sandbox — the
docker daemon resolves that host path against ITS OWN `/tmp`, finds nothing, and the mount fails
("not a directory"). Hit live, first run: `error mounting ".../trunk/.uedcli/tmp/....ini" ... not a
directory`. Moving only the trunk (not the golden — golden is only ever produced via `docker cp`,
never bind-mounted) to `_scratch/` fixed it. `meta.json`'s `status` field (`extracting` → `building`
→ `complete`) is the source of truth for "is this cache entry usable" — a killed mid-build run never
reads as a hit.

**Trunk extraction needed a small addition beyond `ingest_dx_trunk.py`'s own output.**
`ingest_dx_trunk.py`'s own docstring says it is explicitly "NOT a materialize-grade ingest" — actor
classes can come out of UCC batchexport BARE (e.g. `Class=LevelInfo` instead of
`Class=Engine.LevelInfo`; live-confirmed on `DX.dx`'s `LevelInfo` actor, first run of this tool).
`gather_lights`/`ClassDefaults` (needed for the golden's `LIGHT APPLY` and for native's own lighting
build) require every actor's class fully qualified. Fixed by reusing the SAME production mechanism
the real ingest gate (`uedcli/cli/ingest.py`) already uses —
`classindex.ClassIndex.qualify_and_validate`, run once as a post-extraction step — not a new
qualification scheme.

**No hardcoded per-level registry.** The level key is derived from the input `.dx`'s own filename
(`parity_pipeline.level_name`); the pipeline attempts the SAME generic extract-then-self-build
recipe for any input. Whether a given level's pipeline actually completes is a runtime fact — a
clean, named `PipelineError` (never a raw traceback) on the first stage that fails, not a
precomputed allowlist. So far UNATCO and Wanchai are proven end to end (below); anything else is a
live bet on the same mechanism, exactly as the task asked for.

**Two review-round fixes, both reproduced live before and after the fix, same numbers either way for
the already-verified cases.** (1) `ensure_golden` trusted a bare `actors/`-exists check for trunk
completeness — a crashed/partial extraction (per-actor writes are individually atomic, the whole set
is not) would pass that check and get silently reused as a full trunk on the next run. Fixed with an
explicit `.extraction-complete` marker, written only after extraction AND class-qualification both
finish (`parity_pipeline._TRUNK_COMPLETE_MARKER`/`trunk_is_complete`). (2) `compare_lighting`'s
record count used `min(native, golden)` as the denominator — a native lighting build that produces
FEWER records than the golden (including zero) silently shrank the denominator instead of showing a
shortfall, so a badly broken native lighting build could still report `FULL PARITY: YES` if geometry
happened to match. Fixed to always use the golden's own record count as the denominator; any index
the native side lacks simply never counts as identical.

## Live verification

**End-to-end (extraction → class-qualify → self-build → compare) against `DX.dx`** (the trivial
5-brush intro/logo screen, shipped `dev/games/substrate-deusex/Maps/DX.dx`) — first real run of the
tool, cache MISS: geometry EXACT on all 6 counts (nodes/surfs/leaves/verts/points/vectors all
26/26/5/250/32/6, d=+0 everywhere), lighting 26/26 (100%) `LightMap` records byte-identical,
1536/1536 (100%) shadow bits, **FULL PARITY: YES**. Matches the findings ledger's existing "`DX.dx`
... node/surf/leaf-exact" observation and extends it to full byte parity including lighting.

**Caching verified live.** Same input, second run: `[parity] cache hit: ... (skipping trunk
extraction + golden build)`, wall clock **1.5s** (vs the first run exceeding the harness's own 120s
foreground-command threshold and auto-backgrounding — extraction + a real `MAP REBUILD`+
`LIGHT APPLY` editor round trip). Re-verified with a fresh `--json` run: `cache_hit: true`,
`full_parity: true`, byte-identical numbers to the text report.

**UNATCO — reproduces the ledger's numbers exactly, but only against `03_NYC_UNATCOHQ.dx`, not
`01_NYC_UNATCOHQ.dx`.** Deus Ex ships UNATCO HQ as several per-mission-stage `.dx` snapshots
(`01_`/`03_`/`04_`/`05_NYC_UNATCOHQ.dx`, each a different actor/geometry state of the same physical
level). Running this tool against `01_NYC_UNATCOHQ.dx` (the literal "UNATCO" file name) completes
end to end cleanly but does NOT match the historical baseline (1470 actors/721 raw brush actors vs
the historical trunk's 1437/734; nodes d=+350, NOT geometry-exact) — because the historical
`_scratch/bsp-parity-proj/maps/unatco` trunk this whole investigation calls "UNATCO"/"01_NYC_UNATCOHQ"
was actually extracted from **`03_NYC_UNATCOHQ.dx`** (confirmed by raw byte search: `01_...dx`
contains `AlexJacobson`/lacks `AllianceTrigger`; `03_...dx` contains `AllianceTrigger`/lacks
`AlexJacobson`, matching the historical trunk's actor names exactly). Filed as
`board/inbox/unatco-baseline-trunk-is-actually-03-nyc`. Running THIS tool against
`03_NYC_UNATCOHQ.dx` reproduces the ledger exactly: nodes/surfs/leaves EXACT (6314/3616/762,
d=+0 each), verts d=+5, points d=+16, vectors d=+0, lighting 2797/3345 (83.6%) byte-identical,
shadow bits 3729140/3756584 (99.27%), **FULL PARITY: NO** — matching
`unatco-verts-points-residual-after-the-zone`/`line-clear-shadow-ray-algorithm-gap-found-real`'s
own most recent figures bit for bit.

**Wanchai — comparison math verified against the confirmed golden; the LIVE self-build crashed 3/3
tries in this environment.** Three separate `MAP REBUILD`+`LIGHT APPLY` self-builds of
`06_HongKong_WanChai_Market.dx` (1303-brush trunk) all crashed identically — `error: UnrealEd has
crashed — a 'Critical Error' dialog is open`, always at the level's first `EDIT PASTE` (right after
`MAP NEW`, before any rebuild step even starts). This is a reproducible failure in the SHARED,
already-proven `build_ued_lit_golden.py` harness this tool delegates to (not new code), surfaced
cleanly as a `PipelineError` naming the stage and log path each time — no raw traceback reached the
CLI, which is itself a real (if unwanted) proof the error-handling requirement holds under genuine
failure. Filed as `board/inbox/wanchai-self-build-edit-paste-crash`. To still verify the
COMPARISON half on real Wanchai-scale data, `golden.dx` was seeded from the pre-existing,
provenance-confirmed `_scratch/wanchai-relight-2026-08-29/golden.dx` (see
`native-materialize-findings.md`) while the TRUNK was this tool's own live extraction (not copied) —
result: nodes/surfs/leaves EXACT (11648/5284/3371), verts +74, points +16, vectors −8, lighting
3418/4530 (75.5%) byte-identical, shadow bits 2463120/2493200 (98.79%), **FULL PARITY: NO** —
matching `wanchai-verts-points-residual-independently`'s own most recent figures bit for bit.

## Running it

```
.venv/bin/python dev/docs/spikes/2026-08-31-native-parity-report/harness/parity_report.py \
  dev/games/substrate-deusex/Maps/01_NYC_UNATCOHQ.dx
```

`--json` for machine-readable output; `--rebuild-timeout SECONDS` to raise the golden-build bound
for a very large level (default 3600s). Unit tests (not part of `bin/test` — this lives under
`dev/docs/`, not the `uedcli` package `bin/test` collects):

```
.venv/bin/python -m pytest dev/docs/spikes/2026-08-31-native-parity-report/harness/test_parity_lib.py
```
