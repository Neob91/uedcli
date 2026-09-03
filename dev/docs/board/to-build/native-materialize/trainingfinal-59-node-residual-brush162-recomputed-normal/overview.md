+++
priority = "p1"
kind = "debug"
summary = "TrainingFinal -59 node residual localized to Brush162 recomputed-normal ULP drift"
+++

# TrainingFinal -59 node residual localized to Brush162 recomputed-normal ULP drift

`00_TrainingFinal` (764 world-CSG brushes), baseline at `1b8be83`: native vs cached lit golden
`d_nodes=-59 d_surfs=+0 d_leaves=-11`. Live prefix binary search
(`spikes/2026-09-03-built-parity-worst-tier/harness/tf_prefix_search.py`, log committed): first
diverging brush is **`Brush162` (world-CSG idx 686)** — n=686 exact, n=687 `-107/+0/-13`, then
n=689 `+42`, n=692 `+57`, full `-59` (cancellation). The 2026-09-01 static lead
(`Brush907`/`909`/`911`/`915`, idx 660-668, `area51-entrance-residual-localized-to-brush1852`) is
**disproven as the first divergence: n=668 is exact.** (The old GC-dialog `_wait_idle` blocker is
fixed; the search ran clean.)

## Measured mechanism

`Brush162`: 6-poly Yaw=32768 `CSG_Add` sloped panel at `(7358,-4256,56)`;
`MainScale`/`PostScale` carry only `SheerAxis=SHEER_ZX` (rate 0 ⇒ identity ⇒ unscaled marshal
path). At n=687 its fragment COUNT matches (8 == 8) but the sloped surf plane differs:

- native  N `(-5.8080545e-08, 0.66436398, 0.74740899)` = `[0xb379743c, 0x3f2a13c2, 0x3f3f5632]`
- editor  N `(-5.8080534e-08, 0.66436386, 0.74740934)` = `[0xb3797439, 0x3f2a13c0, 0x3f3f5638]`

Authored local normal is `(0, -0.664364, 0.747409)`; a 180° yaw maps it exactly (sign flips), so
the x≈-5.8e-8 on BOTH sides proves both RECOMPUTE the normal from the winding — and disagree by
2-6 ULPs per component; `pBase` z differs ~8e-6; the fragments' split verts shift 0.01-0.06. The
final n=687 trees diverge at 69 sync-walk origins, mostly count-neutral ULP-plane pairs on
45°-normal planes (native `0.70714/0.70707` vs editor `0.70711/0.70711` — same
recompute-disagreement shape), owner diffs smeared over ~150 brushes, net `-107`.

**Minimal case (live, `minimal_golden.py`): [`Brush663`, `Brush1`, `Brush162`]** (its two
bbox-overlap partners, both Yaw=32768) — counts EXACT (50/29/25 both) yet the surf normals carry
the IDENTICAL bit divergence as the full level (same three hex values each side). The mechanism is
fully isolated in 3 brushes; the count damage only appears once the tree is big enough for the
shifted planes to flip splitter picks.

## Classification

KNOWN thread — the unscaled-brush authored-vs-recomputed normal family
(`UEDCLI_BSPCSG_ADD_RECOMPUTE_NORMAL`; the 2026-09-02 f32-chain round measured its remaining 73
ULP nodes on UNATCO and noted "editor value consistent with CalcNormal-derived"). TrainingFinal is
the first level whose whole node residual is localized to it. The lever: pin the editor's exact
recompute site + op order (CalcNormal → SafeNormalSlow f32 chain) for split fragments of unscaled
brushes, and match it bit-for-bit; the 3-brush case above is the cheap live oracle for candidate
fixes (surf-normal bits, no tree needed).

Evidence: spike `2026-09-03-built-parity-worst-tier` §7, `tf-prefix-search.log`.

## Verified 2026-09-03: the [`Brush663`, `Brush1`, `Brush162`] oracle is now bit-exact, the level is not

`321f5dd` (the merged Vandenberg fix: float32-π sine table + uniform `SNS(X·CalcNormal(local))`
face-normal rule) closes the mechanism this item names, at the oracle: rerunning the minimal
3-brush case against current native, the sloped surf's normal is now bit-identical to the pinned
editor value on all three words (`0xb3797439/0x3f2a13c0/0x3f3f5638`), where before it differed by
2-6 ULPs per component. Probe: `tf_brush162_normal_probe.py` (added alongside this note).

That does NOT close TrainingFinal. Offline native-vs-cached-golden baseline (`tf_prefix_search.py
baseline`, current native): `d_nodes=+158 d_surfs=+0 d_leaves=-17` — unchanged from the number
already recorded post-fix in `area51-nsfhq-trainingfinal-node-delta-magnitude`, not this item's own
`-59/+0/-11` (that number is now stale/pre-fix). Per the spike's own finding, this brush's normal
was one of "~150 brushes" carrying the same recompute-ULP family smeared across the level — fixing
one brush's bits does not move a diffuse many-brush aggregate. Whether `Brush162` is still the
first divergent brush in the full-level order (as opposed to the isolated oracle) is unverified:
that needs a live editor rebuild of the n=687 prefix, and no `uned` editor container is available
in this environment. Tracking the level number moved to `area51-nsfhq-trainingfinal-node-delta-magnitude`;
this item's remaining scope is narrower than its title now suggests — the recompute-site mechanism
is confirmed and fixed, TrainingFinal's residual needs its own fresh localization pass.
