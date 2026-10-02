+++
priority = "p2"
kind = "debug"
summary = "Pass B builds SELF-portals (leaf X to itself) at nodes whose `iLeaf[0] == iLeaf[1]`, and `leaf_portal_map` files each in BOTH directions where `AddPortal` files one — so one always clears the `d < 0` gate and the permeating-light flood loops forever. Masked by a `front_leaf != back_leaf` stopgap in `zones::make_portals_clip`; owed a faithful fix."
spikes = ["dev/docs/spikes/2026-09-06-island-n123-portal-graph/"]
+++

# Portal graph builds self-portals from stale `iLeaf` pairs

Found 2026-09-06 while porting Pass B faithfully (`dev/docs/spikes/2026-09-06-island-n123-portal-graph/`).
The old `zones::collect_portals` dropped any fragment with `front_leaf == back_leaf`; `AddPortal`
(`Editor.dll 0xa72a0`) has no such test, so the faithful port removed it — and WanChai N=35 stopped
terminating.

## What happens

WanChai N=35 has 8 BSP nodes (355..363) whose `iLeaf[0]` and `iLeaf[1]` are **the same leaf, 71** —
in UED22's own shipped package as much as in native's (the two are byte-identical there, so this is
not a native artefact). `FilterThroughSubtree`'s two phases can therefore both land on leaf 71:
phase 0 descends `iChild[0]` down the 355→363 chain to node 363, which is terminal on both sides with
`iLeaf = (71, 71)`, while phase 1 lands directly on node 355's `iLeaf[1] = 71`.

Native then produced 23 such self-portals (287 portals against the old code's 264), and
`permeating_lights::leaf_portal_map` files EVERY portal in both directions — `b -> a` with the node
plane's normal and `a -> b` with it negated. For a self-portal that is two entries on leaf 71 with
opposite normals, so one of them always clears `ActorVisibility`'s `d < 0` gate, and clipping a
polygon by the beam through itself returns it unchanged: the flood recurses leaf 71 → leaf 71
forever. Measured: 35M+ `actor_visibility` calls, still on light 0, pinned at the 4096 depth guard;
the WanChai N=35 native build went from ~13 s to >25 min without finishing.

The editor files the same record ONCE: `AddPortal` writes the single `this+0x10050[iLeaf]` slot twice
(`iFrontLeaf == iBackLeaf`), and `GetPolyForLeaf` always reverses it (`iLeaf == iFrontLeaf`), so the
editor gets one orientation, not both.

## The stopgap in place

`zones::make_portals_clip` drops `front_leaf == back_leaf` again, commented as a stopgap. That is
what native has always done, so it changes nothing against master — but it is a mask over an
algorithmic divergence and is owed a faithful fix.

## What the faithful fix needs

Two unknowns, both cheap to settle with an editor probe:

1. **Does the editor build these fragments at all?** Its `Portalize` (`0xaa370`) re-runs
   `AssignLeaves` (`0x100aa480`) immediately BEFORE `MakePortals` (`0x100aa4f1`), which should give
   every node a fresh, self-consistent `iLeaf` — yet the package it ships still has
   `iLeaf = (71, 71)` on a node with a real `iChild[0]`, which no `AssignLeaves` walk produces. So
   either the re-run does not reset `iLeaf` for a side that now has a child, or a later pass
   restores the stale pair. Decide it by dumping `AddPortal`'s `(iFrontLeaf, iBackLeaf)` pairs from a
   live `MAP REBUILD` under `winedbg` (INT3 at `Editor.dll 0xa72a0`) and looking for `(71, 71)`.
2. **If it does build them**, `leaf_portal_map` must file a self-portal once, reversed, the way
   `GetPolyForLeaf` hands it over — and the flood then needs whatever actually stops the editor from
   looping on it (most likely the single orientation failing the `d < 0` gate).

Native's own `iLeaf` bookkeeping is not the bug: it matches UED22's byte for byte. What is missing is
the editor's `AssignLeaves` re-run at portalize time, which native has no equivalent of at all.

## Repro

    UEDCLI_PORTAL_PROF-style instrumentation removed; to reproduce, delete the `front_leaf ==
    back_leaf` guard in `zones::make_portals_clip` and run
    actor_parity.py --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx native 35
