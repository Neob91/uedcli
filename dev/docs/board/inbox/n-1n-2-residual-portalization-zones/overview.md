+++
priority = "p2"
kind = "implement"
summary = "N-1→N-2 residual: portalization/zones (`TestVisibility` §8)"
+++

# N-1→N-2 residual: portalization/zones (`TestVisibility` §8)

p2. The portal golden
(case f) fails Tier-S: native is single-zone (1 leaf, no zone split), the editor makes 4 zones / 3
leaves / 16 nodes from the portal brush. The portal NotSolid force (§5) IS applied; the missing
piece is the zone flood (`sub_aa370`'s ~8 passes — output-format decoded, algorithm not). This is
the same N-2 single-zone→multi-zone slice. Tracked by xfail `test_case_f_portal_residual`. Leaf
COUNT parity for multi-region carves (golden c=6 leaves) is the same slice (native emits 1).
