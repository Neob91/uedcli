+++
priority = "p1"
kind = "debug"
summary = "Native zone OVER-FRAGMENTATION — SPLIT into two causes; the flood bug is FIXED, a CSG-tree cause REMAINS (this is the real bottleneck)"
+++

# Native zone OVER-FRAGMENTATION — SPLIT into two causes; the flood bug is FIXED, a CSG-tree cause REMAINS (this is the real bottleneck)

Root-caused 2026-07-19 with an isolation
oracle (`harness/zone_flood_oracle.py`) that runs native's Pass B/C flood on the EDITOR's OWN tree,
and pinned §70 §13. **(1) FIXED — zone-portal OVER-MARKING (`zones.rs`, in-lane):** native flagged a
face a zone boundary whenever the generating node's surf was `PF_Portal`, using the WORLD-sized
infinite quad clipped to the whole cell — over-marking a small portal surface's entire cell face. On
the Catacombs EDITOR tree this falsely zone-marked 1084 within-zone faces → 56 zones vs editor 17.
The editor's `BlockPortal` (§3) stamps only the leaf-pairs the `PF_Portal` node's REAL polygon
covers; ported as `collect_zone_barriers` (real-poly re-filter through the coplanar-chain HEAD's
subtrees). Now editor-exact leaf-pair-wise on ALL FOUR editor trees (interior zones 3/6/4/16 =
editor); castle byte-identical; regression `tests/test_zone_flood.py`. **(2) REMAINS — native's CSG
tree is geometrically SHATTERED (`bspcsg.rs`/`passes.rs`, OUT of the zones lane):** the oracle's
pure-adjacency `[D1]` (union EVERY portal, ignoring the zone flag) still finds **44** disconnected
leaf-blobs on NativeUnatco and **25** on NativeCatacombs where the editor's own tree is 4/3 — whole
rooms are portal-DISCONNECTED (14–18 leaves have ZERO portals), insensitive to `MIN_AREA`
(1.0→0.001 gives 44→41). No flood change can merge leaves that share no face. So native UNATCO stays
45 zones AFTER the fix, and the UNATCO load-hang suspicion rides on cause (2), NOT the flood.
**ROOT-CAUSED 2026-07-19 — see §87 `87-cause2-shattered-tree.md`.** Cause (2) is Pass-1
OVER-SOLIDIFICATION: a golden cross-tree PointRegion probe (`harness/shatter_probe.py`, validated
`[A]=0` on the byte-identical castle) shows native fills as SOLID **74.5 %** of the editor's OPEN
space on HK Market, 15.3 % UNATCO, 9.7 % Catacombs — and `[A]` is IDENTICAL pre- vs
post-repartition (`UEDCLI_BSPCSG_NOREPART`), so the root is Pass-1 incremental `bsp_brush_csg`, NOT
repartition/merge/find_best_split (all ruled out) and NOT `zones.rs` (proven byte-faithful). The
mechanism is the `is_csg_filter` dead-node hack (superseded — see below): an FWTB-DEAD face buried
solid-on-both-sides by overlapping ADDITIVE brushes wrongly keeps
flipping `Outside`, so later additive fragments in genuine void are mis-classified `F_INSIDE`,
dropped, and the void mis-labels solid. TRIGGER = overlapping-additive burial (castle has 23.2 %
dead nodes but `[A]=0` — dead-node COUNT is not it; the malignant kind is additive-buried). The
disconnection/entombment is the downstream consequence. **Next action:** the scoped fix in §87 §7 —
tag FWTB-deleted faces buried solid/solid vs subtract-divider and make `is_csg_filter` transparent
for the buried kind; re-verify castle byte-identity + N=4..8 soup; add a dense overlapping-additive
level to the differential loop. Module: `bspcsg.rs` ONLY (MEDIUM effort; deeper order-faithful
re-port is the LARGE fallback). Evidence: §87 + §70 §13; reproduce `harness/shatter_probe.py` +
`harness/overlap_discriminator.py`. (Found 2026-07-18; split + flood-half fixed, cause-2 pinned
2026-07-19.)

> **Superseded 2026-08-28** — the `is_csg_filter` dead-node hack this item named has been
> eliminated, not "scoped": commit `b3609ea` restored the editor's `NumVertices>0` clause to
> `is_csg_filter` (`bspcsg.rs:477`), exactly the remedy §87 proposed. The HK"Market 74.5 %
> over-solid probe ([A] probe) is independent corroboration; the Wanchai resolution
> (`wanchai-bsp-gap-localized-to-one-dropped` §9) caught the same mechanism live. Re-measure the
> `[A]`/over-fragmentation numbers on OG trunks (UNATCO, Wanchai) before acting on this item's
> remaining text. The two spike sections (82, 87) that validate the old drop are stale — flag for
> owner approval to correct (dev/docs/spikes not agent-editable).
