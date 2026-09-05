+++
priority = "p2"
kind = "bug"
summary = "Island (01_nyc_unatcoisland) N5-N12 FAIL the parity gate on master (world Model2 orphan-vert +4 / points +1), contradicting the 'byte-exact N1..12' claim. A separate, smaller orphan overcount than the OceanLab N3 Pass-D coplanar bug — not fixed by that fix."
+++

# Island N5-N12 pre-existing Model2 orphan-vert +4 residual

Found while corpus-validating the OceanLab N3 Pass-D orphan-vert fix
(`oceanlab-n3-model2-orphan-vert-overcount-shifts`), 2026-09-05.

## Symptom

On master (pre-fix native), `parity_gate.py` FAILS for Island N5..N12 (freshly-built editor refs via
`actor_parity.py ... ref N`). Island N1..N4 pass. This contradicts the recorded "Island byte-exact
N1..12" (MEMORY / task premise). Methodology validated: UNATCO N8 passes vs its shared cached ref, and
OceanLab N1/N2 pass — so the Island refs are sound and the failures are real.

## Counts (Island N8, decode `umodel.parse_model_body` Model2)

- native (both master AND the OceanLab-fix branch): verts **511**, points **79**
- UED22 ref: verts **507**, points **78**
- nodes 45=45, live-ring slots 186=186, vectors 18=18 match.

So a **+4 orphan-FVert** overcount and **+1 point**, world Model2, on structure-exact Island cells.
One contiguous orphan run (`[180..480)` native vs `[180..476)` editor).

## Not the OceanLab Pass-D coplanar bug

The OceanLab fix (`e836e6d`, Pass D uses precise `FilterThroughSubtree`) changed Island N5..N12's
orphan iVertex VALUES but NOT the orphan COUNT (511 both before and after) — so this +4 is a DIFFERENT
mechanism than the coplanar-drop that closed OceanLab's +85. Candidates: the `>14` `SplitInHalf` edge,
a `bspAddPoint` NEAR-pool point-resolution difference (+1 point), or a different Pass-D/optgeom nuance.
Needs its own diagnosis; not addressed by the OceanLab fix.

## Repro

`_scratch/reg/{old,new2}/01_nyc_unatcoisland_N8.dx` vs
`_scratch/actor-parity/01_nyc_unatcoisland/ref_N8.dx` (worktree `worktree-agent-a05dd19140b6194f5`);
or rebuild via `actor_parity.py --dx .../01_NYC_UNATCOIsland.dx {native,ref} 8` + `parity_gate.py`.
</content>
