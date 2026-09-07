+++
priority = "p3"
kind = "implement"
summary = "DONE -- step 6 is ported, with FSceneNode::ViewSides rebuilt from ComputeRenderSize and pinned against a live capture of all six gather frames."
spikes = ["dev/docs/spikes/2026-09-07-oceanlab-n48-lightbits/", "dev/docs/spikes/2026-09-06-boundvisible-port/"]
+++

# Port `URender::OccludeBsp`'s frustum-cone subtree reject — DONE

`visible_surfs.rs` now applies the reject (`render.dll 0x1001979b`–`0x10019884`) at the editor's own
point: on the chain HEAD, after the near subtree has run, abandoning the node's surface, the rest of
its coplanar chain and its far child. `FSceneNode::ViewSides[4]` is rebuilt the way
`FSceneNode::ComputeRenderSize` builds it (`Engine.dll 0x1013295d`) and matches all 24 live-captured
components on all six gather faces (`view_sides_match_the_live_editor_gather_frames`).

It was not what closed UNATCO N=26's descendant of this item — the missing ZONE RETIRE was (see
`oceanlab-n48-world-model2-lightbits-differ-on`) — but the two together bring native's box-test count
to exactly the editor's on OceanLab N=48.
