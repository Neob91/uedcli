+++
priority = "p2"
kind = "debug"
summary = "FIXED — Pass F is a NODE walk over `PF_Portal` surfs reading `Node.iZone[0]/[1]`, not a portal-fragment walk that skips zone 0. OceanLab N=154 -> 155."
spikes = ["dev/docs/spikes/2026-09-07-oceanlab-n153-temp-brush-rsp/"]
+++

# OceanLab N=155 — world `Model2` `Zones[0]`/`Zones[1]` connectivity misses each other

The only residual: two `Zones` connectivity masks. Native `0x01`/`0x82`, UED22 `0x03`/`0x83` — zone
0 and zone 1 are mutually connected in the editor's build and not in native's. `leaves` (so every
leaf's `iZone`), `nodes`, `points` and `surfs` were byte-identical, which rules the zone ASSIGNMENT
out and points at Pass F alone.

Native built connectivity from the Pass-B portal FRAGMENT list, filtered by the zone-barrier set,
and skipped any pair with `za == 0 || zb == 0`. `FEditorVisibility::BuildConnectivity`
(`Editor.dll 0xa7960`, decoded in
`dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/passesEFG-8850-7960-7e60.md` Pass F)
does neither: it walks the NODES, takes every node whose surf has `PF_Portal` (`0x100a79f7`), and
ORs `Zones[iZone[1]] |= 1<<iZone[0]` plus the mirror (`0x100a7a23`). Zone 0 is not special-cased.

Ported as `zones.rs::build_connectivity`. Regression:
`zones.rs::portal_node_connects_zone_zero_to_its_other_side`.
