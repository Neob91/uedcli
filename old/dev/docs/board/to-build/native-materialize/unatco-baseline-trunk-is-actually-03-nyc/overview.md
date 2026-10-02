+++
priority = "p2"
kind = "debug"
summary = "The 'UNATCO' baseline trunk (_scratch/bsp-parity-proj/maps/unatco, nodes=6314) this whole investigation has been citing as 01_NYC_UNATCOHQ.dx was actually extracted from 03_NYC_UNATCOHQ.dx — confirmed by raw byte search. 01_NYC_UNATCOHQ.dx is a different, real map and gives different (not node-exact) numbers."
+++

# UNATCO baseline trunk is actually 03_NYC_UNATCOHQ.dx, not 01_NYC_UNATCOHQ.dx

Found while building and live-testing the new parity report tool
(`dev/docs/spikes/2026-08-31-native-parity-report/`) against the shipped original
`dev/games/substrate-deusex/Maps/01_NYC_UNATCOHQ.dx` — the file this session's own docs
(`native-materialize-findings.md`, several board items) call "UNATCO" / "01_NYC_UNATCOHQ".

Deus Ex ships UNATCO HQ as several separate `.dx` files, one per mission-progress revisit:
`01_`, `03_`, `04_`, `05_NYC_UNATCOHQ.dx` — same physical location, different actor/geometry state
each time. This tool's fresh extraction of `01_NYC_UNATCOHQ.dx` (1470 actors, 721 raw `Class=Brush`
actors) does NOT match the historical `_scratch/bsp-parity-proj/maps/unatco` trunk this
investigation has used throughout (1437 actors, 734 world brushes) — a large actor-name mismatch
(e.g. `AllianceTrigger0/1/2` and `Brush1153`/`Brush1277`/… exist in the historical trunk but not in
`01_NYC_UNATCOHQ.dx` at all; `AlexJacobson0` and `Brush215` exist in `01_NYC_UNATCOHQ.dx` but not
the historical trunk).

Confirmed by raw byte search across the four numbered files:

| file | contains `AllianceTrigger` | contains `AlexJacobson` |
|---------------------|---|---|
| `01_NYC_UNATCOHQ.dx` | no  | yes |
| `03_NYC_UNATCOHQ.dx` | yes | no  |
| `04_NYC_UNATCOHQ.dx` | no  | yes |
| `05_NYC_UNATCOHQ.dx` | no  | yes |

The historical trunk's own actor set matches `03_NYC_UNATCOHQ.dx` (has `AllianceTrigger`, lacks
`AlexJacobson`). Running the new parity tool against `03_NYC_UNATCOHQ.dx` reproduces the ledger's
own most recent UNATCO figures exactly: nodes/surfs/leaves EXACT (6314/3616/762), verts d=+5, points
d=+16, vectors d=+0, lighting 2797/3345 (83.6%) byte-identical, shadow bits 99.27% — bit-for-bit the
same numbers `unatco-verts-points-residual-after-the-zone` and
`line-clear-shadow-ray-algorithm-gap-found-real` (round 9) report.

**Not fixed here** — out of scope for the tool-building task that found it. Whoever next touches the
UNATCO thread should either (a) rename/re-anchor the investigation's "UNATCO" references to
explicitly say `03_NYC_UNATCOHQ.dx` (the file actually measured), or (b) decide `01_NYC_UNATCOHQ.dx`
should be the real target and re-run the whole UNATCO analysis chain against it — a materially
different, and NOT node-exact, geometry starting point (d_nodes=+350, d_surfs=+3, d_leaves=+39
against a fresh self-built `01_NYC_UNATCOHQ.dx` golden, measured live this session). Either way, is
an owner/coordinator call, not one this item makes.
