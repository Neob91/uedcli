# The permeating-light beam clip now takes `FPlane`'s own orientation — the sign-sum heuristic is gone

**Result: the departure was real, the faithful port landed, and it moves almost nothing.** The five
ladder ceilings are unchanged (UNATCO 162, NYC_Bar 152, Island 122, OceanLab 47, WanChai 44), no
level's blocker is closed by it, and Island N=123 is unaffected. Measured, the heuristic and the
faithful plane disagreed on **7 of 7166 clip edges** on NYC_Bar N=152 — every one a *degenerate*
edge where the editor has no interior to prefer either.

## What "sign-sum" meant

`FEditorVisibility::ActorVisibility` narrows the portal poly it is about to cross by the beam from
the light through the poly it entered by: per edge `(ClipPoly->Vertex[jPrev], ClipPoly->Vertex[j])`
it builds `FPlane(Actor->Location, Vertex[j], Vertex[jPrev])` and keeps `SplitWithPlaneFast`'s front
half. `FPlane(A,B,C)`'s normal is `((B-A) ^ (C-A)).SafeNormal()`, so its SIGN comes from the clip
poly's vertex winding and nothing else.

`permeating_lights::clip_beam` built the same cross product, then **negated the plane whenever the
clip poly's own vertices summed to a negative signed distance** (`sign_sum < 0.0`). That forces
"the kept half is the beam interior" for either winding. It was added when native's portal polys
came out of an ad-hoc `plane_axes` basis with no winding guarantee; the 2026-09-06 `MakePortals` port
removed that excuse, and the note it left ("dropping the heuristic is the faithful next step ... it
moves every permeating-light decision on every level") is what this pass settles.

## The two orientations are the same thing wherever the geometry is well-formed

For a planar CONVEX clip poly with the light strictly off its plane, the beam plane through one edge
splits space so the polygon's other vertices are all on ONE side, and which side is fixed by the
light's height above the polygon plane:

    n · (P - L) = t · ((W ^ e) · (P - Vj))       n = (Vj-L) ^ (Vjp-L),  e = Vj - Vjp,
                                                 W = winding normal, t = (L-Q)·W

`(W ^ e) · (P - Vj) > 0` is exactly "P is interior" for a poly wound about `W`, so `sign(n·(P-L)) =
sign(t)`: the plane faces the interior iff the light is on the PLUS-winding side. (Checked
numerically over 20 000 random convex polys, 110 283 edges, both light sides: 0 disagreements on the
plus side, 110 094 of 110 094 on the minus side.)

Native's portals satisfy that invariant. `zones::build_infinite_fpoly` spans its quad
`(Base ± Axis1·W) ± Axis2·W` with `Axis2 = Axis1 ^ N`, so `Axis1 ^ Axis2 = -N` and the stored poly's
winding normal is MINUS its `Normal`; `MakePortalsClip`/`FilterThroughSubtree` and
`split_with_plane_fast` all preserve vertex order; `leaf_portal_map` reverses normal and winding
together, exactly as `FPortal::GetPolyForLeaf`'s `Reverse()` does. And `actor_visibility` only
crosses a face whose `d = (L - Base)·Normal < 0`, i.e. with the light on the plus-winding side.
Measured on NYC_Bar N=152: **418 of 418 portals** have winding normal opposed to `Portal.normal`,
none the other way.

So the heuristic was inert on every well-formed edge — which is why the ladder does not move.

## Where they differed: degenerate clip edges

All 7 disagreements on NYC_Bar N=152 are edges of a *clipped* clip poly whose two endpoints are
near-duplicates — `edgelen` between `3.0e-5` and `2.4e-4` world units:

| `sign_sum` | clip edge length | clip poly |
|-----------:|-----------------:|---|
| -5.23e-1 | 2.44e-4 | `(-1702.2979,-384,56) (-1704,-384,56) (-1704,-384,57) (-1703.9998,-384,57)` |
| -1.19e+2 | 3.81e-5 | 5 verts on `x = -1560`, two of them `4e-5` apart |
| -5.50e+0 | 3.05e-5 | 5 verts, two `3e-5` apart |
| -2.04e+0 | 3.05e-5 | 5 verts, two `1e-5` apart |

(each appears twice — the same beam reached from two portals). `SafeNormal`'s `SMALL_NUMBER = 1e-8`
cutoff is on the SQUARED cross product, and at these edge lengths the cross product is still ~6e-3
long, so it survives and gets normalized to unit length: the resulting plane direction is pure f32
rounding. Native reproduces the editor's cross product bit for bit (same `(B-A)^(C-A)` term order,
same `SafeNormal`), so it lands on the same noise plane — unless the heuristic negates it, which is
the only thing that can make the two engines disagree here.

## The disassembly (`core.dll 0xb440` — `FPlane::FPlane(FVector,FVector,FVector)`)

`ret 0x24` = three by-value FVectors at `[ebp+8]` (A), `[ebp+0x14]` (B), `[ebp+0x20]` (C). It forms
`D = B-A` and `E = C-A` component-wise and then `D ^ E`:

```text
0x1000b446  movss xmm4,[ebp+0x18]     ; B.y
0x1000b458  subss xmm4,[ebp+0xc]      ; D.y = B.y - A.y
0x1000b467  subss xmm6,[ebp+0xc]      ; E.y = C.y - A.y
0x1000b48b  mulss xmm0,xmm6           ; D.z*E.y
0x1000b490  mulss xmm1,xmm3           ; D.y*E.z
0x1000b49e  subss xmm1,xmm0           ; (D^E).x = D.y*E.z - D.z*E.y
0x1000b4c8  call 0x10051090           ; FVector::SafeNormal
0x1000b4e3..0x1000b50b                ; W = (A.y*N.y + A.x*N.x) + A.z*N.z
```

No interior test, no conditional negate. The call site's argument order is likewise re-confirmed:
`Editor.dll` pushes `Vertex[jPrev]` (`0x100a70c0`), then `Vertex[j]` (`0x100a70f0`), then
`Actor->Location` (`0x100a7117`), each with its own `sub esp,0xc` — so the LAST written sits lowest
and is arg `A`.

## Verification

- Full `ladder_run.py --from 1 --to <ceiling>` re-walk on all five, every N rebuilt against the new
  binary: **UNATCO N=1..162, NYC_Bar N=1..152, Island N=1..122, OceanLab N=1..47, WanChai N=1..44 —
  all PASS.** No N regressed; every ceiling is where it was.
- The next N of each level still fails on its own recorded blocker — UNATCO 163, NYC_Bar 153,
  WanChai 45, OceanLab 48, Island 123 — none of which this touches.
- **Island N=123 is unchanged**: still `BODY model model2`, still leaf 26's extra permeating run.
  The 2026-09-06 spike predicted this (the heuristic took no flip on any of the six edges of the
  decisive beam) and the measurement confirms it. Its open item stands as written.

## Pinned

- `uedcli/tests/test_engine_facts.py::test_permeating_light_beam_planes_are_normalized_and_stop_clipping_at_14_vertices`
  now also pins the six `core.dll` encodings above (the `(B-A)^(C-A)` order).
- `permeating_lights.rs::clip_beam_orientation_comes_from_the_clip_polys_winding` — the same target
  poly is kept through a correctly-wound clip poly and rejected whole through the reversed one. The
  shared `beam_clip_poly()` fixture was re-wound to match the real invariant (winding normal opposed
  to the face normal, light on the plus-winding side); with the heuristic in place its winding did
  not matter, which is why the old fixture was wound the other way.

## Files

- `uedcli-native/src/permeating_lights.rs` — the change.
- `harness/flip_probe.patch` — the temporary `PROBEFLIP`/`PROBEWIND` instrumentation (not applied).
