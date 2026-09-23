# `actor survey` — CSG-kind coverage, Intersect/Deintersect, collision tolerance, bounded cost

Closes four of the open items in `dev/docs/board/to-spec/actor-survey-and-actor-relation-csg-resolved/spec.md`.
Everything below is measured against real code and real shipped content; where something is still
unconfirmed it says so instead of rounding up to an answer.

## What was measured against what

| Artifact | What it is | Where |
|---|---|---|
| the native CSG core | `uedcli_native.build_geometry_bspcsg`, the faithful `bspBrushCSG` port the parity campaign holds to byte-identity with UED22 | `uedcli-native/src/bspcsg.rs` |
| class defaults | the git-tracked UED22 package corpus (`Engine.u`, `DeusEx.u`, `DeusExDeco.u`, …) | `uned/UED22/*.u` |
| real levels | 23 shipped level trunks extracted by earlier campaign work — Deus Ex and original Unreal, 5 to 2111 brushes | `_scratch/geo-confirm-*/maps/*/`, `_scratch/bsp-parity-proj/maps/*/`, `_scratch/proj/maps/*/`, `_scratch/u1-photos/maps/*/` (gitignored) |

The level trunks are gitignored, so every number derived from them is committed here as JSON
(`collision-clearance.json`, `bounded-cost.json`, `bounded-cost-small.json`) next to the harness
that produced it.

The native extension was rebuilt from this worktree's own Rust source before the final runs
(`UEDCLI_VENV=$PWD/.venv bin/test`), so no result rests on a stale `.so`.

## 1. CSG-kind coverage

### How the kinds are really encoded

`ECsgOper` has five ordinals — `Active=0, Add=1, Subtract=2, Intersect=3, Deintersect=4`
(`uedcli-native/src/csg.rs`). **Semisolid and Nonsolid are not operations at all**: they are
`CSG_Add` plus an actor-level `PolyFlags` bit, `PF_Semisolid = 0x20` / `PF_NotSolid = 0x08`
(`uedcli/builders.py`, `dev/docs/unrealed/quirks.md` "Solidity rides `PolyFlags`"). That is exactly
what `query.csg_kind` already implements.

### What each kind contributes — measured, not reasoned

Harness: `harness/kind_semantics.py`. One level, three brushes, trunk order
`Room (1024³ Subtract) → Pillar (128×128×512, the kind under test) → Cutter (Subtract over the
pillar's right half)`. Solid/void is the engine's own collision walk (see the `PointRegion` trap
below); "area" is the pillar's own surviving world-soup face area.

| kind | pillar's left half solid? | right half (inside the Cutter) solid? | own faces, uncut → cut | own area, uncut → cut |
|---|---|---|---|---|
| add | yes | **no** | 6 → 11 | 294912 → 229376 |
| **semisolid** | **yes** | **yes** | 6 → **6** | 294912 → **294912** |
| **nonsolid** | **no** | no | 6 → 11 | 294912 → 229376 |
| subtract | no | no | 0 → 0 | 0 |
| **intersect** | no | no | **0 → 0** | **0** |
| **deintersect** | no | no | **0 → 0** | **0** |

Read off that table:

- **Semisolid contributes real solid matter, and no Subtract in the trunk can ever carve it.** The
  editor runs every Add/Subtract in its LOOP 2 and only then, after the repartition, the semisolid
  brushes in LOOP 3 (`csgRebuild`; native's `detail_pass`, `bspcsg.rs`). Trunk order is irrelevant —
  a semisolid is always applied last. Its faces still get *cut by* the already-carved world (that is
  what "receives cuts but emits no world-splitting planes" means), but its own matter is never
  removed.
- **Nonsolid contributes no solid at all.** `derive_nf` sets `NF_NotCsg` from `PF_NotSolid`, so a
  nonsolid node never bounds solid space and the collision walk passes straight through it
  (`dev/docs/unrealed/quirks.md`: "only nonsolid is walk-through"). Its *faces* are real world
  surfaces and a later Subtract removes them exactly as it would an Add's — measured above, same
  area loss.

- **A placed Intersect/Deintersect contributes nothing to the world**: no face, no solid, no node.
  The resulting model is node-for-node identical to the level without it. See §2.

**One live doc contradiction, recorded rather than smoothed over.** `dev/docs/unrealed/quirks.md`
and `leveldesign/kb/csg-bsp.md` say a semisolid blocks like solid and is fully walkable;
`dev/docs/spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md` says the opposite ("you
collide with the face, but the space behind/around it isn't solid"), and repeats it in
`2026-07-15-native-materialize/sections/10-bsp-csg-build.md`. The older claim is marked as
mechanism-level inference, not a traced predicate. **This spike settles only the zero-extent case**:
for a point query, a semisolid node is `IsCsg`-solid and the walk reports solid, measured above. The
EXTENT (box) path is different code — `FBoxLineCheckInfo::BoxLineCheck` produces its hit from the
terminal leaf's convex hull via `iCollisionBound`, with `IsCsg` used only to route — and whether
`bspBuildBounds` gives a thin semisolid slab a hulled solid leaf is untraced by anyone. So the
contradiction is narrowed, not closed. Nothing here depends on the untraced half: `crosses` needs
"is this point inside solid", which is the zero-extent question.

### The `PointRegion` trap

`native/materialize._model_point_region` (`UModel::PointRegion`) is **not** a solidity oracle. A
semisolid's nodes are added after `TestVisibility` has assigned leaves and zones, so a semisolid's
interior carries no leaf of its own and `PointRegion` reports the surrounding void's leaf for it —
measured: the semisolid row above reads "void" under `PointRegion` and "solid" under the collision
walk. Semisolid is ~29% of brush actors in shipped Deus Ex content, so this is not an edge case.

What the engine itself uses in a collision trace is `FBspNode::IsCsg` plus the walker's running
outside state, never a leaf index and never a `PolyFlags` read. `harness/solidity.py` is that walk,
ported from `uedcli-native/src/linecheck.rs` + `collision.rs`. The first version of this spike's
collision measurement used `PointRegion` and was wrong; the trap is pinned by a test so the next
reader does not repeat it.

### Frequency in shipped content

Parsed every `actor.t3d` header across the corpus (28,232 actors, 16,796 brush-bearing), applying
`csg_kind`'s own rule:

| kind | count | share of brush actors |
|---|---:|---:|
| add | 6,891 | 41.0% |
| **semisolid** | **4,943** | **29.4%** |
| subtract | 4,004 | 23.8% |
| nonsolid | 491 | 2.9% |
| mover (brush actor of a Mover class, no `CsgOper`) | 456 | 2.7% |
| add with no `CsgOper` at all (class default `CSG_Active`) | 11 | 0.07% |
| **intersect / deintersect** | **0** | **0%** |

### Rulings this supports

- **Semisolid**: a valid `crosses` source and a valid `crosses` target — it is solid matter and its
  faces bound solid. **Never the target of `carves`**, at the `csg` tier, ever. Raw `carves` will
  claim it whenever trunk order looks right, and the `csg` tier correcting that is a textbook case
  of what the two-tier design is for.
- **Nonsolid**: never a `crosses` source and never a `crosses` target — it bounds no solid, and
  walking through it is the engine's designed behaviour, not an intrusion. It *is* a valid `carves`
  target: a later Subtract genuinely removes its faces. It stays a valid `touches` participant as
  long as the other side contributes solid.
- **Intersect / Deintersect**: contribute nothing, so they can be neither source nor target of any
  `csg`-tier relation, and can never be the container side of `contains`. See §2 for the warning.

## 2. Intersect / Deintersect — what "warn" should mean

**The spec's stated reason for the risk is wrong, and the real reason is narrower.** The spec says
Intersect/Deintersect "can affect resolution outside a single actor's immediate neighborhood". They
affect nothing outside themselves — they affect nothing at all. `bspBrushCSG` dispatches
`CsgOper == 3 || 4` to a tail that wipes and refills **the brush actor's own `UModel`**
(`Result = Actor->Brush->Brush; Result->EmptyModel(1,1); GModel = Result;`, `Editor.dll 0x35ab3`,
decoded in `dev/docs/spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`);
the world model is never touched. Native reaches the same outcome by returning before LOOP 1/2
(`bspcsg.rs`), and the measurement in §1 confirms the world is node-identical with and without one.

So the real risks are these three, all local to the actor carrying the oper:

1. Its whole `csg` tier is empty of any fact it could source, and that emptiness is correct but
   surprising.
2. Its `raw` tier is actively misleading: `actorgraph.classify_pair` branches on
   `query.csg_is_subtract` alone, so an Intersect brush falls into the "Add-or-Mover" bucket and
   gets `touches`/`contains`/`carves` edges as if it were solid.
3. `uedcli` cannot author one (`brush build --csg` offers `add|subtract` only; `brush intersect`/
   `deintersect` are stateless builder verbs). One can only arrive via an imported map — and zero
   exist in 16,796 shipped brush actors.

**Concrete rule.** `actor survey <name>` prints its full output and exits 0. When **the surveyed
actor itself** is an Intersect or Deintersect brush, it writes one extra stderr line naming the
actor and the oper, saying that a placed `CSG_Intersect`/`CSG_Deintersect` contributes nothing to
the resolved world (the editor treats it as a builder-brush operation on its own model), so its
`csg` tier carries no fact it sources and its `raw` tier treats it as Add-like, which the resolved
world does not. **No other actor's survey warns**: an Intersect contributes nothing, so it cannot
change anyone else's facts — a neighborhood scan for one would be pure noise.

This is a stderr warning beside a complete answer, which the `CLAUDE.md` "no silent half-answers"
rule would normally refuse. It is allowed here because the answer is not partial: the actor really
has no `csg`-tier source facts, and the warning explains a correct emptiness rather than papering
over a missing computation. Recorded because the owner ruled "warn on Intersect/Deintersect".

## 3. Collision extent and the `crosses` tolerance

### The extent is a box, not a cylinder

`Scout::extent()` (`uedcli-native/src/collision.rs`) is
`Vec3::new(collision_radius, collision_radius, collision_height)` — UE1 collides an **axis-aligned
box of half-extents `(R, R, H)`**, and `UModel::PointCheck`/`LineCheck` take exactly that extent.
"Collision cylinder" is the property names' vocabulary, not the engine's geometry. The spec should
say collision extent / collision box.

### The measurement

Harness: `harness/collision_clearance.py`; results `collision-clearance.json`. For every non-brush
actor with `bCollideActors` and a nonzero `R`/`H` (resolved instance-else-class-default, exactly as
`serve/scene.py::_actor_radii` does), the world is resolved natively and the actor's **signed
uniform clearance δ** is found by bisection: the largest amount its box can be grown (δ > 0) — or
must be shrunk (δ < 0) — to be entirely in void, tested on a 27-point sample of the box.

**Coverage, and what was excluded and why.** 23 level trunks were walked; the numbers below come
from the subset where every actor's class-default resolution succeeded. Two kinds of trunk were
dropped, both recorded in the JSON per level as `class_unresolved`:

- **The original-Unreal trunks** (`showcase_*`, 8 of the 24). Their classes are not in `uned/UED22`,
  so 120–277 actors per level fail class-default resolution and any that do resolve may resolve
  against the wrong class. Measured and reported in the JSON, but not evidence, and not mixed into
  the totals.
- **Deus Ex trunks extracted with BARE class names** (`Class=ATM` rather than `Class=DeusEx.ATM`).
  `ClassDefaults.for_class` correctly refuses an unqualified class, so every actor in those trunks
  is unresolved. Where the same map also exists as a qualified extraction (`wanchaimkt` vs
  `wanchaimkt-q`) the qualified one is used; `wanchaimkt-q` is itself dropped as a duplicate of
  `wanchai`, the same map under another project dir.

What is left is every Deus Ex trunk that resolves cleanly, with zero resolution failures.

Six distinct maps survive that filter — `unatco`, `oceanlab-lab`, `wanchai`, `nsfhq04`,
`vandenberg-gas`, `paris-club` — 1522 collidable actors between them.

| gate | actors | clear (δ ≥ 0) | penetrating | p50 depth | p90 | max |
|---|---:|---:|---:|---:|---:|---:|
| `bCollideActors` (the spec's current gate) | 1522 | 1272 (84%) | 239 (15.7%) | 8.8 uu | 52.1 uu | 436 uu |
| `bCollideActors` **and `bBlockActors`** | 1051 | 927 (88%) | 122 (11.6%) | 7.8 uu | 12.7 uu | **64.2 uu** |
| `bCollideActors` and `bCollideWorld` | 892 | 802 (90%) | 88 (9.9%) | 10.6 uu | 13.8 uu | 64.2 uu |
| `bCollideActors` and NOT `bBlockActors` | 471 | 345 | 117 (24.8%) | 11.4 uu | 96.1 uu | 436 uu |

(`buried` — the box's own centre inside solid — is 11 actors under the loosest gate and 2 under
`bBlockActors`; those saturate at the shrink floor and are excluded from the depth percentiles.)

Depth histogram, uu, for the two gates that matter:

| gate | < 0.001 | 0.001–0.01 | 0.01–0.1 | 0.1–0.5 | 0.5–1 | 1–2 | 2–4 | 4–8 | 8–16 | 16–32 | ≥ 32 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `bCollideActors` | 0 | 0 | 4 | 15 | 8 | 40 | 20 | 27 | 74 | 17 | 34 |
| **+ `bBlockActors`** | 0 | 0 | 3 | 7 | 5 | 15 | 12 | 21 | 55 | 2 | 2 |

### What the numbers say

**There is no float-noise band to tolerate.** Not one of 1522 real collidable Deus Ex actors
penetrates solid by less than 0.01 uu; the smallest real penetration measured anywhere is
**0.043 uu** (0.052 uu among blocking actors). An actor either clears solid outright (84–90%) or is
inside it by a visible amount. So no tolerance *derived from content* exists: the distribution is
continuous from there to 64 uu with no gap to cut at, and a tolerance large enough to suppress the
by-design cases (p90 = 12.7 uu even under the tightest useful gate) would suppress real mistakes
too.

**What does cut the noise is the source gate, not a tolerance.** `bCollideActors` alone admits
trigger volumes — `DataLinkTrigger` at `R = 520`, `FlagTrigger` at `R = 630`, `LaserTrigger`,
`OrdersTrigger`, `Engine.Teleporter` — deliberately sized to span rooms, walls included. They are
471 of the 1522 and they carry the entire deep tail: excluding them drops the maximum from 436 uu
to 64 uu and p90 from 52 uu to 12.7 uu. The engine's own name for "this actor's extent occupies
space others cannot" is `bBlockActors`, and that is the right gate. `bCollideWorld` is tighter still
but wrong: it drops 279 genuinely physical wall- and ceiling-mounted props
(`HKHangingLantern2` ×88, `SecurityCamera` ×28, `HKBirdcage` ×26, `Keypad1`, `AlarmUnit`,
`ClothesRack`) whose `bCollideWorld` is false only because they are mounted and never fall; the
converse set is 3 actors (a `Cat` and a `GasGrenade`).

**The tolerance that is left is bounded from below by the engine, not by content.** Resolved point
coordinates are only reproducible to the CSG point-dedup thresholds — `THRESH_POINTS_ARE_SAME`
0.002 uu and `THRESH_POINTS_ARE_NEAR` 0.015 uu (`bspcsg.rs`). Nothing below that is a meaningful
geometric distinction in a resolved model. So the `csg` tier's coincidence tolerance is
**0.015 uu**, the engine's own resolution limit — comfortably under the 0.043 uu smallest real
penetration, so it never suppresses a real fact, and it absorbs everything that truncation or a
different BSP split could move (§4). This supersedes the spec's "same `_TOUCH_EPS` class" wording
for the `csg` tier; `_TOUCH_EPS = 1e-3` stays correct for the raw tier, which works on authored
brush vertices rather than resolved points.

**The residual is ~12%, and it is a true fact.** Under the `bBlockActors` gate, roughly one in eight
physically-blocking actors really is inside solid, by ~8 uu at the median — flush-mounted
`CageLight`, `Keypad1`, `Toilet`, `VendingMachine`, `ClothesRack`. The open item feared this would
"fire constantly". It fires on one in nine, and `actor survey` is a single-actor report, not a
level-wide lint: one extra true line about the actor you asked about is not the noise problem a
level scan would have. To make it readable rather than merely true, the fact carries the measured
depth in the existing annotation grammar — `crosses(8.2uu)` — so 8 uu of flush mounting reads
differently from 60 uu of misplacement.

## 4. Bounded cost

### What it actually costs today

Harness: `harness/bounded_cost.py`; results `bounded-cost.json`.

| level | brushes | trunk load | full CSG solve | whole-level raw graph |
|---|---:|---:|---:|---:|
| `dx` | 5 | 0.08 s | 0.07 s | 0.01 s |
| `nyc-shipfan` | 111 | 0.99 s | 0.14 s | 2.11 s |
| `nyc-underground04` | 132 | 0.85 s | 0.18 s | 1.51 s |
| `wanchai-garage` | 201 | 0.83 s | 0.27 s | 2.10 s |
| `nyc-bar` | 208 | 1.13 s | 0.17 s | 2.11 s |
| `nsfhq04` | 1035 | 4.49 s | 1.28 s | — |
| `wanchai` | 1331 | 7.94 s | 3.45 s | — |
| `oceanlab-lab` | 1925 | 6.69 s | 10.16 s | — |
| `showcase_chizra` | 2111 | 10.16 s | 6.67 s | — |

- The **`csg` tier was never the cost problem.** A full-level solve is about the same as the Python
  trunk read every uedcli verb already pays, and an order of magnitude less than it on the largest
  trunks measured (41 s on a 1437-actor UNATCO trunk).
- The **`raw` tier is the expensive one.** At 208 brushes its whole-level graph already costs 12×
  the full CSG solve, and it is `O(brushes²)` — no level above 208 brushes was timed because the
  sweep does not finish in a reasonable time, which is itself the answer.
- **Scoped**, one survey costs a median **6 ms** for the `csg` tier (worst 46 ms) and a median
  **31 ms** for the `raw` tier (worst 5.5 s, on a surveyed actor whose neighborhood was unusually
  large) — three orders of magnitude below either whole-level pass.

### The neighborhood algorithm

```
R  := actor_bounds(surveyed) grown by PAD
N  := [ a for a in level.order if a.brush and aabb_intersects(actor_bounds(a), R) ]   # trunk order
      ... plus, always, the level's FIRST world-CSG brush
csg facts := solve_world_surfaces(N), read only inside R
raw facts := decompose the surveyed brush + each near a in N, classify_pair(surveyed, a)
```

`actor_bounds` and `aabb_intersects` already exist (`uedcli/writes.py`), and
`preview_native.solve_world_surfaces` already takes an ad-hoc ordered actor list — this is a
selection rule over shipped parts, not new machinery.

**The first-brush clause is not cosmetic — it was found by the measurement failing without it.**
`bsp_brush_csg` special-cases a leading `CSG_Add` against a node-less world: it SEEDS that brush as
the world shell, storing every face reversed, instead of classifying it (`bspcsg.rs`'s
`first_add_seed`, whose own comment records that this is right for the box a level opens with and
wrong for anything else, measured against the live editor 2026-07-25). Truncation changes which
brush is first, so the shortcut fires on the wrong one. Concretely, surveying `nsfhq04`'s
`DeusExMover31` over its 3 neighbours: the full solve has four `Brush799` faces in the region, the
truncated solve had none of them and one `Brush798` face instead — a genuine structural divergence,
not float noise. Forcing the level's own first world-CSG brush into `N` makes the shortcut fire on
exactly the brush it fires on in the full solve, and the divergence disappears. (`brushcsg.
build_scaffolding` hits the same trap for `brush deintersect` and solves it a different way, by
prepending a distant synthetic Subtract; either works, and reusing the level's own first brush needs
no synthetic geometry.)

### Why the truncation is sound

**Locality.** A CSG operation changes the world's solid/void labelling only inside its own brush
volume. That is what `bspBrushCSG` does and nothing more: LOOP 2 filters the brush's own polys
through the world tree, so only fragments inside the brush are added; `FilterWorldThroughBrush` cuts
only world faces interior to the brush, and native's port is already **bound-sphere pruned** —
it descends only the subtree the brush's `FSphere` straddles, verified against `Editor.dll 0x33250`
with byte-identical output (`bspcsg.rs`). Outside the brush's bound nothing is added, removed, or
split.

Therefore the labelling restricted to R after the full ordered brush list equals the labelling
after applying only the sublist whose volumes meet R — every other brush is the identity on R.
Surviving faces are the boundary of that labelling, so the faces inside R are the same surfaces.
The AABB test is a conservative superset of "volume meets R", so N is a superset of the exact set,
and trunk order is preserved, so the relative order of the operations that do matter is unchanged.

**What the argument does not cover, stated rather than hidden:**

1. **Poly identity.** A different tree shape splits the same surface into different polygons. Facts
   must be read from geometry, never from a poly index or a face count. The spec already cut `:idx`
   from the `csg` tier for an unrelated reason; this is a second, independent reason it has to stay
   cut.
2. **Point dedup.** `bspAddPoint`'s `FindNearestVertex` descends the *live* tree, so dropping far
   brushes changes which existing point a new point welds onto — by at most the dedup thresholds,
   0.002 uu / 0.015 uu. This is exactly why the `csg` tier's tolerance is 0.015 uu (§3): every
   perturbation truncation can introduce is already inside the tolerance band.
3. **Global passes.** `zone_pass`, `bspOptGeom`'s point merge and shared-side counter, the bounds
   pass and the canonical surf reorder are all whole-model. Zone *numbers* therefore differ in a
   truncated solve. No survey relation may read one: in particular `connects` must be decided by
   local face existence between the two Subtracts, never by zone identity. The point-merge half
   folds into risk 2.
4. **The first-Add seed.** Not covered by the locality argument at all — it is a property of the
   list's first element, not of any brush's volume. Handled by the first-brush clause above, which
   the measurement forced.

### The empirical check

For each sampled actor the harness compares the full-level solve against the truncated solve by
**face signature**: every surviving face clipped to R, area accumulated per `(owner actor, owner
poly index)`, compared key-for-key with a 1e-4 relative area tolerance. Faces are matched by owner
and area rather than by polygon identity on purpose — a different split of the same surface is not
a divergence.

Where an area does differ, the harness then measures how far the surface's BOUNDARY actually moved,
rather than guessing from the area alone: both sides are different subdivisions of one planar
surface, so the polygons within each side are disjoint and `area(A ∩ B)` is exactly the sum of the
pairwise clips. The symmetric-difference area divided by the perimeter is the implied boundary
displacement — the number to hold against the point-dedup thresholds. (A vertex-to-vertex distance
was tried first and is useless here: a split vertex on one side has no counterpart on the other, so
it reports the length of a whole edge, up to 48 uu, for surfaces that are geometrically identical.)

**110 surveys over 11 levels (782–2111 brushes), 10 randomly chosen brush actors each. No face is
ever missing and none is ever extra.** The neighborhood is a median 0.5% of the level's brushes
(worst 5.6%), and the truncated solve takes a median 6 ms against 1.3–10.2 s for the full-level one.

Nine of the 110 show an area difference on one or two faces. Their measured boundary displacement:

| survey | faces differing | symmetric difference | implied boundary shift |
|---|---:|---:|---:|
| wanchaimkt `Brush2407` | 1 | 0.0016 uu² | 0.00009 uu |
| showcase_chizra `Brush380` | 1 | 0.016 uu² | 0.00012 uu |
| wanchai `Brush1817` | 3 | 0.041 uu² | 0.00021 uu |
| nsfhq04 `Brush298` | 1 | 0.015 uu² | 0.00028 uu |
| showcase_sunspire `Brush1629` | 3 | 0.11 uu² | 0.00043 uu |
| oceanlab-lab `Brush664` | 2 | 0.008 uu² | 0.00053 uu |
| nsfhq04 `Brush818` | 2 | 0.32 uu² | 0.0012 uu |
| oceanlab-lab `Brush1333` | 2 | 1.02 uu² | 0.024 uu |
| **paris-chateau `Brush1076`** | **1** | **224 uu²** | **0.25 uu** |

Eight of the nine are boundary noise: ≤ 0.024 uu, i.e. at or just above the 0.015 uu dedup
threshold and far below the 0.043 uu smallest real content feature (§3). That is exactly the
perturbation risk 2 predicts, at the magnitude it predicts.

**The ninth is not noise, and its cause is a known native defect rather than the truncation rule.**
`Brush996` is a SEMISOLID whose −Y face is exactly coplanar with the surveyed `Brush1076`'s +Y face;
what survives of it inside the region is a 1-uu-wide frame around `Brush1076`'s footprint. The full
solve keeps that frame over `z = 16…209`; the truncated solve keeps only `z = 128…209`. No brush is
missing from `N` — every brush whose AABB meets the lost sliver is in it, checked directly.

The `z = 128` cut names the cause. `paris-chateau` opens with `Brush963`, a 256³ Add at the origin
in a map spanning ±3000 — not the world shell. `bsp_brush_csg` seeds a leading Add as the world
shell, storing its six faces reversed as structural splitters, and its own comment records that this
is WRONG for exactly this case (a leading Add that is a small solid, measured against the live
editor 2026-07-25, tracked as the `first_add_seed` board item). Both solves fire that shortcut on
`Brush963`, so both carry its `z = ±128` planes; in the full solve they are buried under a thousand
later brushes, in the seven-brush truncated solve they dominate the tree, and a hairline semisolid
fragment coplanar with an adjacent Add lands on the wrong side of the seeded `z = +128` plane and is
dropped.

So the truncation inherits `first_add_seed`'s known wrongness and, on a small tree, amplifies it.
The alternative — prepending a distant synthetic Subtract so no Add ever meets an empty tree, which
`brushcsg.build_scaffolding` already does for `brush deintersect` — would suppress this case, but it
would also make the truncated solve differ from native's own full solve by design rather than match
it. The real fix is the tracked `first_add_seed` one; `actor survey` should not paper over it.

**A second sweep over the six SMALLEST trunks (5–208 brushes, 30 more surveys) adds one more
structural case, and it is the same shape.** Surveying `nyc-underground04`'s `Brush6`, the truncated
solve gains a face the full solve does not have: `Brush8`'s poly 0, a 32×4 rectangle lying exactly
on `z = −400`, which is exactly `Brush6`'s own bottom-face plane. Nothing is missing, and no brush is
absent from `N`.

**Both structural residuals — 2 in 140 surveys — are exact-coplanar ties.** In each, the divergent
face lies exactly on an adjacent brush's face plane, where survival is decided by
`AddBrushToWorldFunc`'s coplanar cases (`F_COSPATIAL_FACING_IN`/`_OUT`, plus the semisolid exception)
against whatever the live tree happens to be. A smaller tree can decide such a tie the other way.
**The constraint this puts on the implementation**: `touches`/`crosses` must be decided by plane
coincidence within the tolerance, not by "does a face exist here" — a redundant coplanar face
appearing or vanishing must not change a reported fact. Read that way, neither residual changes
an answer.

## Still open

- **Whether a Mover may be a `crosses` source.** The factual half is settled: a Mover is excluded
  from world CSG entirely (`brush_marshal._in_world_csg`; the editor's own iteration filter is
  `AActor::IsStaticBrush`), so it contributes no solid to the world, can never be carved, and can
  never be the *target* of a world `crosses`. But it does carry a real private `UModel` of genuine
  solid matter (`unbuilt.build_mover_shape_model`, byte-verified against the UNATCO golden), and
  that matter can extend into world solid — a door embedded in its frame at the base pose is the
  normal case, the same by-design-overlap shape as §3's flush-mounted props. Whether that should be
  reported is a design call, not a measurement, and it belongs to the owner. Parked as
  `questions/mover-as-a-crosses-source.md` on the board item.
- **Two spec changes this spike introduced from measurement**, flagged for the owner rather than
  assumed: the `crosses` collision-source gate tightening from `bCollideActors` to
  `bCollideActors && bBlockActors`, and the `crosses(<depth>uu)` annotation. Parked as
  `questions/collision-source-gate-and-depth-annotation.md`.
- **The `first_add_seed` residual.** Not opened by this spike and not closed by it: the leading-Add
  world-shell shortcut is a known-wrong native path with its own board item, and the truncated solve
  is more exposed to it than a full solve because its tree is small. One of 110 surveys hit it, on a
  1-uu sliver of a semisolid face. Worth re-measuring once `first_add_seed` is fixed, rather than
  worked around in `actor survey`.
- **A production home for the solidity walk.** `harness/solidity.py` and the copy in
  `uedcli/tests/test_csg_kind_facts.py` are Python ports of a Rust routine that already exists
  (`CollisionModel::point_check`) but is not exposed to Python. Per the Rust-by-default convention
  the real implementation belongs in `uedcli-native` as a point/box solidity query; that is a
  plan-time item, not a spike finding.

## Regressions

`uedcli/tests/test_csg_kind_facts.py` pins every checkable fact above against the native core:
Add contributes solid and is carved; semisolid contributes solid and is never carved; nonsolid
contributes no solid but its faces are carved; a placed Intersect/Deintersect leaves the world
node-identical; and `PointRegion` is not a solidity oracle for semisolid.

## Harness

| file | what it does |
|---|---|
| `harness/corpus.py` | corpus discovery, the UED22 class index / class defaults, trunk loading |
| `harness/solidity.py` | the engine's own point-in-solid walk over a parsed `umodel.Model` |
| `harness/kind_semantics.py` | §1 — what each CSG kind contributes and whether a later Subtract carves it |
| `harness/collision_clearance.py` | §3 — signed clearance of every collidable actor in the corpus |
| `harness/bounded_cost.py` | §4 — per-tier cost and the truncation-vs-full-solve check (`--smallest` reaches levels where the whole-level raw graph finishes) |

Run from the repo root with the worktree venv, e.g.
`.venv/bin/python dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/kind_semantics.py`.
The three corpus-driven scripts need the gitignored level trunks; their committed JSON output is the
durable record.
