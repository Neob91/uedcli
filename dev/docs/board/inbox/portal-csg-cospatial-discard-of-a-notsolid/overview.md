+++
priority = "p2"
kind = "unknown"
summary = "Portal CSG: cospatial discard of a NotSolid-forced portal's side faces + multi-zone `TestVisibility` (`0xaa940`)"
+++

# Portal CSG: cospatial discard of a NotSolid-forced portal's side faces + multi-zone `TestVisibility` (`0xaa940`)

p2. Blocks corpus case **f** (portal). Two sub-unknowns: (1) the
portal box's 4 side faces sit coplanar with the room walls; the editor DROPS them but native's
`AddFunc` keeps them as `F_COSPATIAL_FACING_IN` (§4.3 says keep-unless-semisolid, and a
Portal is forced NotSolid not Semisolid) — so either the decoded keep-set is incomplete for the
portal-forced-NotSolid path, or a later pass drops them; needs a live differential to pin which.
(2) `TestVisibility`'s multi-zone flood (`0xaa940` → `sub_aa370`'s ~8 passes) is only
output-format decoded (§8), so f's 2-zone split across the `PF_Portal` face is not reproducible;
native emits single-zone (§8.3). f additionally needs the `bspOptGeom` item above (walls split at
z=±4). See the b/f xfail notes in `tests/test_csg_native_differential.py`.
