+++
priority = "p2"
kind = "debug"
summary = "2026-09-03 per-brush Pass-1 trace round: NO brush diverges on counts; Pass-1 trees structurally identical, divergence was plane VALUES. Two mechanisms CONFIRMED+fixed (GMath table used double PI — 4683/16384 entries wrong; per-face normal = SNS(X·CalcNormal(local)), authored ignored — plus editor-faithful mirror post-transform reversal). Vandenberg +659/+7/+309 -> +397/-1/+238; the residual is localized ENTIRELY to the world bspRepartition (editor enters Pass 2 at 8702 nodes, native 9191; soup sizes 6158 vs 6156). Next: the 2-poly soup diff / repartition scoring."
+++

# Vandenberg count parity was error cancellation

The 2026-09-02 per-brush Pass-1 trace round (`native-materialize-findings.md`, search "UNATCO live
per-brush Pass-1 tree-shape trace") shipped the editor-faithful all-f32 `ABrush::BuildCoords`
transform chain for scaled brushes. Live-gdb validations on Vandenberg's own `Brush54` (412-poly
dome): all 412 post-`FPoly::Transform` normals and 339/412 Base values match ONLY the new chain's
predictions (0 match only the old double compose; the editor's Transform input normal is
`calc_normal(local)`, 119/119 decidable).

Despite bit-exact per-poly world inputs, Vandenberg's counts move AWAY from its golden:

| | nodes | surfs | leaves | plane-exact |
|---|---|---|---|---|
| old (double chain) | -6 | +0 | -56 | 50/10677 |
| new (f32 chain) | +659 | +7 | +309 | 7/10683 |

Same shape as nsfhq04's `Brush8321` precedent: the near-exact count was two errors cancelling. The
remaining divergence is downstream of the transform (filter/split/merge on this level's 318 scaled
+ mirror brushes; the mirror path is still native-approximated — ring-reverse + `calc_normal` —
rather than the editor's `Orientation`-flip + VectorXform normal, a candidate). Not chased in that
round (UNATCO-scoped task); no fudge/revert per the standing rule.

Next step: per-brush Pass-1 count trace on Vandenberg (`pass1_brush_trace_unatco.py` already
accepts its golden — the k=0..8 normal-probe capture is in
`_scratch/pass1-trace/pass1-normal-probe-golden_vandenberg-gas.log` of the 2026-09-02 worktree;
logs also under `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/`) to find the first
diverging brush the same way UNATCO's was cleared.

## 2026-09-03: the post-merge sweep "regression" IS this item — bisected, not the mover merge

The fresh baseline sweep (tab `2026-09-03T01h49Z`) flagged Vandenberg `010000 -> 000000` vs the
pre-merge tab and attributed it to `8c4950f` (the unbuilt-parity/mover merge). Offline bisect
against the cached golden (same `.dx` both runs): `4c7b72d` builds the OLD numbers
(`-6/+0/-56`), `ccfaaa2` — this item's own f32-chain ship, pushed in the same batch as the merge —
builds the new (`+659/+7/+309`); `8c4950f`'s mover/`rsp_links` content adds nothing on top. No
mover enters or leaves world CSG: the +7 surf delta is 9 semisolid Pass-2 brushes (8 of them the
`Brush154`-family cardinal-multi 10-poly Adds at +1 each, 1 scaled at -1) — downstream cascade of
the Pass-1 tree shift over the level's 318 scaled brushes, matching this item's "compensating
divergence further down" reading. The lighting drop (0.28% -> 0.00%) is the same cascade. Nothing
new to revert; the next step above stands.

Also ruled out (2026-09-03): the corrected `CsgOper::Active` semantics
(`vandenberg-gas-csg-active-csgoper-brush-causes` Round 4) are a strict no-op here — the native
build is sha256-IDENTICAL pre/post that fix (`Brush230` is a lone 1-poly Active brush nothing
overlaps within its one-brush deferral window). The `+659/+7/+309` residual is entirely this
item's f32-chain divergence.

## 2026-09-03: per-brush Pass-1 trace run — two mechanisms fixed, residual localized to the repartition

Full round: `dev/docs/spikes/2026-09-03-vandenberg-first-divergent-brush/spike.md`. The trace found
NO count-diverging brush: all 728 Pass-1 steps agree, final Pass-1 trees structurally identical;
the divergence was 2996 plane-VALUE nodes (first: node 734, k=13 `Brush41`, unscaled unrotated Add).
Fixed (commits `b2199cd`, `a7be107`):

- `rotation.py`'s GMath table built its angle with double π; the editor uses FLOAT32 π —
  4683/16384 entries wrong (up to ~32 ULPs, every non-cardinal index). Live-captured full table
  reproduced 0/16384.
- Per-face normal is `SNS(X · CalcNormal(local))` for EVERY brush poly (importer stores CalcNormal
  over the authored normal — proven from the golden's own Polys bytes; `FPoly::Transform`
  renormalizes unconditionally). Replaces Add-keeps-authored/§48-Subtract-only/dot-guard; mirrors
  now use the editor's post-transform ring reversal (`BrushInput::orientation`).

Pass-1 plane diff 2996 → 65 (all ~1-ULP, mostly `plw`; no count effect — left open). Counts
`+659/+7/+309` → `+397/-1/+238`. The remaining +397 is localized ENTIRELY to the one-shot world
`bspRepartition`: editor enters Pass 2 at 8702 nodes/4118 surfs, native at 9191/3839 (+489 nodes;
the surf gap is orphan-trim timing — the editor later drops the same 279, final surfs d=-1). World
`FindBestSplit` soups: editor 6158 polys (captured,
`2026-08-29-unatco-repart-live-diff/logs/fbs-world-poly-order-vandenberg-gas.log`) vs native 6156 —
next step is diffing those soups (`UEDCLI_BSPCSG_SOUP_ORDER` vs the FBSPOLY capture) and, if they
match, the repartition scoring/recursion.
