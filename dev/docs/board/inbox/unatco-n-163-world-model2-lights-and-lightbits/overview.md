+++
priority = "p2"
kind = "debug"
summary = "UNATCO is byte-exact N=1..162 and bails at N=163: native emits 7 extra Model.Lights entries and 217 extra LightBits bytes, shifting every LightMap record, while every geometry array and the leaves stay byte-exact."
+++

# UNATCO N=163 — 7 extra `Model.Lights` entries and 217 extra `LightBits` bytes

Found 2026-09-07 walking the ladder forward after
`unatco-n-116-world-model2-light-runs-differ-on` turned out not to block the level.

`parity_gate.py`: one failure, `BODY model model2: canonical bodies differ`.

    bbox sphere vectors points zones bounds leafhulls leaves numsharedsides tail   SAME
    nodes surfs verts                                                              masked only
    lightmap lights lightbits                                                      REAL

- `lights` 2166 vs 2159, `lightbits` 182862 vs 182645.
- Every one of the 346 `LightMap` records differs, from index 0, and only in `DataOffset` (+217) and
  `iLightActors` (+7) — a pure shift, so the extra entries sit BEFORE any record's run in both
  arrays.
- `leaves` (93) is byte-exact, so no leaf's `iPermeating` moved.
- `lightrun_diff.py` reports **0 differing runs** across the 346 lightmaps: every run it decodes from
  each side's own record offsets agrees.

So the extra 7 entries and 217 bytes are not in a run `lightrun_diff.py` reaches. Locating them is
the first step — the candidates are the last leaf's permeating run (the only one whose growth moves
no leaf offset) and a surf early in DATA order whose shadow planes grew (`LightBits` is written in
surf-index order while records are allocated in BSP-walk order, so record 0's data starts at 52752,
not 0).

Once located this is most likely the same family as `nyc-bar-n-153-world-model2-lightmap-runs-ued22`
(native a strict superset of UED22's per-surf light set) rather than the permeating flood.

## Repro

    ladder_run.py --dx dev/games/deusex/Maps/03_NYC_UNATCOHQ.dx --from 163 --to 163 --keep-native
    model_dump.py <native_N163.dx> <ref_N163.dx> model2
    lightrun_diff.py <native_N163.dx> <ref_N163.dx>
