+++
priority = "p1"
kind = "debug"
summary = "Breadth geometry check on 10 new OG levels: 1/10 exact (Endgame4)"
+++

# Breadth geometry check on 10 new OG levels: 1/10 exact (Endgame4)

Pure-breadth pass per the standing 30%-floor goal: test previously-untested shipped Deus Ex levels
for exact native geometry, no root-causing. Method: `level import MAPFILE --tree level/NAME`
(bootstraps the trunk directly from the shipped `.dx`, no editor) into a fresh `_scratch/geo-confirm-*`
project, golden via the established VERIFIED-CORRECT `build_ued_golden.py --world-only --no-light
--no-obj-load` (`MAP NEW`→`EDIT PASTE`→`MAP REBUILD`→`MAP SAVE`, never `MAP LOAD` — see the findings
ledger "Golden `.dx` provenance"), compared against `uedcli_native.build_geometry_bspcsg` via the
`breadth_gate.py` node/surf/leaf/vert/point/vector count pattern. All 9 golden builds completed
end-to-end (full logs captured, `MAP NEW`→re-add→`MAP REBUILD`→`MAP SAVE`, no `MAP LOAD`) — provenance
is solid by construction, no retroactive check needed.

## Result

| level | source .dx | brushes | golden nodes | native nodes | Δ nodes | Δ surfs | Δ leaves | exact? |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Endgame4 | `99_Endgame4.dx` | 6 | 46 | 46 | 0 | 0 | 0 | **yes** (fully byte-exact incl. verts/points/vectors) |
| NYC Bar | `02_NYC_Bar.dx` | 203 | 1620 | 1621 | +1 | 0 | 0 | no |
| NYC Underground (04) | `04_NYC_Underground.dx` | 127 | 1858 | 1876 | +18 | 0 | 0 | no |
| Paris Club | `10_Paris_Club.dx` | 344 | 3135 | 3143 | +8 | 0 | 0 | no |
| NYC ShipFan | `09_NYC_ShipFan.dx` | 103 | 1773 | 1861 | +88 | 0 | 0 | no |
| Vandenberg Gas | `12_Vandenberg_Gas.dx` | 870 | 10683 | 11289 | +606 | +2 | -134 | no |
| Wanchai Garage | `06_HongKong_WanChai_Garage.dx` | 198 | 2146 | 1696 | -450 | -141 | -68 | no (severe under-build) |
| Paris Underground | `11_Paris_Underground.dx` | 272 | 2427 | 2017 | -410 | -177 | -32 | no (severe under-build) |
| NYC 747 | `03_NYC_747.dx` | 373 | 4462 | 3870 | -592 | -127 | -146 | no (severe under-build) |
| OceanLab Lab | `14_OceanLab_Lab.dx` | 1886 | 29533 | 23045 | -6488 | -4469 | -3864 | no (severe under-build) |

**1/10 exact.** Endgame4 (23KB, a 6-brush cutscene/logo screen) is exact on every count — the same
trivial-map pattern as `DX.dx`, not a real win for the parity floor but a real confirmation of the
pattern.

## Notes

- **Wanchai Garage / Paris Underground / NYC 747 / OceanLab Lab are a severe-under-build family,
  matching the already root-caused `native-under-builds-area51-entrance-geometry` pattern** (native
  over-carves a CSG-subtract brush's surviving faces, misclassifying some as interior and discarding
  them — confirmed root cause there, not re-investigated here): all four lose double-digit percent of
  nodes AND surfs together (Area51: -26.7%/-8.4%; here -20.9%/-6.6%, -16.9%/-7.3%, -13.3%/-2.8%,
  OceanLab -22.0%/-19.7% — its largest surf-percentage loss of the family), unlike the small
  over-build/under-build noise seen elsewhere in the corpus (≤1% surf delta, usually 0). Not a new
  bug — same family, wider than previously known (now 5/21 levels tested show it, and it scales to
  the largest level tested so far).
- NYC Bar (+1 node, +97 verts, 0 surf/leaf delta) and Paris Club (+8 nodes) are small-magnitude
  over-builds in the same range as the previously-documented UNATCO/paris-chateau/training-final
  pattern — not investigated further.
- NYC ShipFan (+88 nodes, +5% — surf/leaf delta 0) and Vandenberg Gas (+606 nodes, +5.7%, first case
  here with a nonzero surf delta +2 and a NEGATIVE leaf delta -134 alongside a node/vert over-build)
  are over-builds of larger magnitude than the small-noise group but not in the severe-under-build
  family either — a third shape, not investigated further (breadth over depth per the task).
## Updated overall count

Prior corpus (`breadth-geometry-re-check-across-11-og-levels-2`): 2/11 exact (Wanchai Market,
`DX.dx`). Adding this batch of 10 (including OceanLab Lab): **3/21 levels now tested, 3 exact
(14.3%)** — Wanchai Market, `DX.dx`, Endgame4. Both new-exact entries (`DX.dx`, Endgame4) are trivial
cutscene/logo maps (≤6 brushes); excluding those two, real levels stand at 1/19 exact (Wanchai Market
only, ~5.3%). Still below the 30% floor. 21 levels is roughly 70-100%+ of the ~20-30 total OG DX
level estimate, so sample breadth is no longer the limiting factor — the parity RATE is.
