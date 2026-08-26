+++
priority = "p3"
kind = "debug"
summary = "Pass D chain-link order: native keeps a split original in place and appends its extra fragments, the editor kills the original and appends the whole group at the chain tail — 24 nodes' iPlane/iBack differ on UNATCO"
+++

# Pass D coplanar-chain link ORDER differs from the editor

Found while closing the UNATCO node gap (see `csgrebuild-runs-testvisibility-between-the`). With the
zone pass now in the right place, native's UNATCO tree matches the editor's golden on node count,
per-surf node counts, planes, surfs, leaves, zones, bounds and leaf hulls. What is left is a
**link-order** difference inside three coplanar chains: 23 nodes whose `iPlane` and 3 whose `iBack`
point somewhere else than the golden's.

The chains hold the same nodes — same `(iSurf, NumVertices)` multiset, same length — in a different
sequence. Example, the `(0,-1,0,32)` chain headed by node 2168 (26 entries both sides):

```
editor: (552,4) (1024,8) (552,8) (719,4) (552,7) then the 21 Pass-D fragments
native: (552,4) (552,4) (1024,8) (552,4) (552,6) (552,4) (552,8) ... interleaved
```

Cause: `zones.rs`'s Pass D keeps a split original node **in place** (retargeting its ring to the
first surviving fragment, `Emit::OriginalRing`) and appends only the extra fragments. UnrealEd's
`AssignAllZones` instead **kills** the original (`NumVertices = 0`) and appends every fragment,
including the first, at the tail — `bspCleanup` then splices the dead original out of the chain. So
the editor's split originals leave their early chain slot; native's do not.

`reorder_nodes_to_tail` already compensates for the node-ARRAY order (a pure relabel), which is why
the array indices line up; it cannot fix the chain LINKS.

**Not fixed here, deliberately.** `Emit::OriginalRing` is the shape that was validated node-for-node
against the castle golden, and no castle fixture exists in this environment to re-verify a change to
it (see `HANDOFF.md`). Fixing this means porting the real kill-the-original behaviour and re-running
the castle byte-identity gate.
