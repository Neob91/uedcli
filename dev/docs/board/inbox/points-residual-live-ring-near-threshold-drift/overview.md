+++
priority = "p3"
kind = "debug"
summary = "Post the 2026-09-03 points GC, the last points extras on structure-EXACT levels (UNATCO +6, Underground +3, ShipFan +1) are LIVE-ring points created just outside the 0.015 ring pool threshold of the editor's pooled coordinate — value drift, same family as the gated UEDCLI_BSPCSG_ADD_RECOMPUTE_NORMAL thread."
spikes = ["dev/docs/spikes/2026-09-03-verts-points-residual/"]
+++

# Points residual: live-ring near-threshold drift extras

`vp_orphan_evidence.py` (spike `2026-09-03-verts-points-residual`) classifies every remaining
count-residual point as reachable/mixed (live rings or `p_base` name them) with no golden
coordinate within 0.5. Example: UNATCO's `(1071.983642578125, -1023.9992065429688, 240.0)` quad —
~0.016 off the round coordinate, just past the 0.015 ring dedup, so native mints a point where
the editor's ring pooled onto an existing one. `UEDCLI_BSPCSG_ADD_RECOMPUTE_NORMAL=1` closes
ShipFan's +1 and Underground +3 -> +1 but regresses vectors +1 on both (measured 2026-09-03) —
and its default flip is still gated on the live `CalcNormal` capture named in
`lighting-bits-only-divergence-localizes-to`.
