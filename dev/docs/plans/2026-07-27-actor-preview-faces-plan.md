# Plan — `actor preview --faces {wire,flat,textured}`

Implements [`../specs/2026-07-26-actor-preview-textured-faces.md`](../specs/2026-07-26-actor-preview-textured-faces.md)
(spec gate passed; no structural finding in any round). **Read that spec and this plan; between them
they are self-contained.** The spec carries the decisions and their rejected alternatives; this plan
carries the slicing, the file map, and each slice's Done-when.

---

## 0. Shape of the build

**FIVE slices, each one commit whose tests pass with no NEW skips versus the pre-slice baseline.**

```
S1  texframe.py extraction                  <- pure refactor, no user-visible change
S2  the seam + --faces + `flat` complete    <- first usable new mode
S3  --focus over filled modes               <- the two-pass, constant chosen by render
S4  `textured`                              <- GATED on the decoder item's S2b
S5  docs, rationale, board, spec deletion
```

**Baseline to re-measure at S1, not to trust from here:** on 2026-07-27 `bin/test` reported
**3499 passed, 13 skipped, 64 deselected, 1 xfailed**, plus `cargo test` 58 passed. Two other
sessions are active in this repo, so re-measure before asserting any count.

### 0a. BUILD ORDER — this whole plan waits on the decoder item

**Owner decision 2.11: the texture-decoder item builds FIRST, then all of this.** `to-build.md`'s
*Native texture decode* delivers, in its slice **S2b**, the mip-pyramid accessor and the `bMasked`
flag on its typed result. **Implement the ordering as ruled: do not start S1 until that item has
landed.**

*Recorded for the owner, not acted on:* only **S4** has a technical dependency on it. S1–S3 touch no
texture code at all — `flat` reads no textures — so they could in principle land earlier or in
parallel. That is an observation, not a licence to reorder; if the sequencing should change, that is
the owner's call and is parked on `board/inbox.md`.

### 0b. House rules this build must satisfy

**Open `CLAUDE.md`** — this section does not replace it, and the rules below have changed more than
once during this feature's life.

- **This is a FEATURE: build it in a git worktree** branched from the checked-out branch, commit
  locally per slice, **never push the feature branch**, gate, then squash-merge from the main
  checkout. `CLAUDE.md` "Feature worktrees".
- **Commit only your own hunks.** Several sessions work this repo at once; read `git diff <path>`
  before staging, never `git add -A`.
- **Run tests via `bin/test`**, never bare `pytest` (`rules/tests.md`). Host-native, in the venv.
- **No back-compat cruft.** When a symbol moves, every importer moves in the same commit; a
  re-export alias is forbidden.
- **No silent half-answers.** Every failure below refuses with exit 2 naming the offending value.
- **An owner decision is implemented as given.** Decisions 2.1–2.13 in the spec are the owner's; a
  defect found in one is a reason to stop and ask, never to adjust it.
- **Docs move with the slice** that changes behaviour; S5 carries only the cross-cutting sweep.

### 0c. Two mechanisms this build must not get wrong

Both were found by review on earlier drafts and are cheap to re-break:

1. **`rotation.actor_linear` returns `None` as the identity sentinel** (`rotation.py:297-298`). The
   mirror predicate is `M = actor_linear(actor); mirrored = M is not None and det(M) < 0`. A bare
   `det(actor_linear(actor)) < 0` raises `TypeError` on nearly every brush.
2. **`getattr(args, "brush_colors", "csg")` does NOT fire for an existing-but-`None` attribute.**
   Switching the parser to `default=None` therefore needs an explicit `or "csg"` at each of the three
   consumers, or `None` propagates into `_scene_geometry`.

---

## 1. Module map

**Changed**

| file | slice | what |
|---|---|---|
| `uedcli/preview_native.py` | **S1** | `_world_uv_frame` (`:193`), `_tex_basis_default` (`:176`), `_newell` (`:183`), `_poly_flags_int` (`:105`) **move out** to `texframe.py` and are imported back. No behaviour change |
| `uedcli/preview.py` | **S1** | `_face_normal` (`:399`) **deleted** — semantically identical to `_newell`; imports `newell` from `texframe` |
| `uedcli/polyalign.py` | **S1** | two imports re-pointed: `:32` `from .preview import _face_normal`, `:33` `from .preview_native import _world_uv_frame` (used at `:257`, `:330`, `:417`) |
| `uedcli/query.py` | **S1** | `:13` `from .preview import _face_normal` re-pointed |
| `uedcli/tests/test_polyalign.py` | **S1** | `:445` imports `_world_uv_frame` from `preview_native`; re-point |
| `uedcli/tests/test_preview_native.py` | **S1** | three `_world_uv_frame`/`_tex_basis` imports (grep `_world_uv_frame`); re-point |
| `uedcli/preview.py` | **S2** | the `PreviewData` seam; the `faces=` parameter on `render_brush_pgm`, `render_brushes_pgm`, `render_quad_pgm`; the scanline fill; the depth buffer; the CSG cull; the `flat` edge rule |
| `uedcli/dispatch.py` | **S2** | `_preview_render_data` restructured (its `return {}` early exit at `:1038-1039` makes the new work unreachable); mover-ness resolved here via the existing `_mover_index`; `faces=` threaded through `_render_breakdown_grid`'s `_pane` |
| `uedcli/cli.py` | **S2** | `--faces` added to `_preview_opts` (`:686`, `:1476`, `:1513`); `--brush-colors` `default=None` (`:155`); the `--brush-colors`, `--focus` and `--show` help strings corrected (`:155`, `:190`, `:199-205`) |
| `uedcli/tests/test_actor_preview.py` | **S2** | `_prev` (`:28`) hardcodes `brush_colors="csg"` and lacks `faces`; migrate |
| `dev/docs/spikes/2026-07-24-corpus-brush-idioms/render_brushes.py` | **S2** | `:186` calls `dispatch._render_actors_to_out` with a namespace (`_args_for`, `:92-96`) lacking `faces`. A committed harness is durable evidence (`rules/spikes.md`), so it migrates with the seam |
| `uedcli/preview.py` | **S3** | the `--focus` two-pass and its composite |
| `uedcli/preview.py`, `uedcli/dispatch.py` | **S4** | the texel path: UV per vertex, mip pick, masking gate, the texture payload on the seam |

**New**

| file | what |
|---|---|
| `uedcli/texframe.py` | stdlib-only shared home for `world_uv_frame`, `tex_basis_default`, `newell`, `poly_flags_int` (S1) |
| `uedcli/tests/test_preview_faces.py` | the `--faces` behaviour tests (S2–S4) |
| `dev/docs/rationale/preview.md` | the agent-side choices (S5) |

**Deliberately untouched:** `builders._newell` (`builders.py:82`) — `texframe` imports `builders`
for `_tex_basis`, so making `builders` import from `texframe` would close an import cycle. That is
the reason, not the `Vec3` annotation an earlier draft gave. `render.rs` and the whole `--native`
tier: this plan changes no Rust and no perspective renderer.

---

## 2. Ground truth measured for this plan (2026-07-27)

- `_mover_index(args, verb, project=None)` (`dispatch.py:3079`) already exists, already resolves the
  index, and already emits **a clean exit 2 naming the verb** when the games config is missing. It is
  the seam decision 2.13 needs; nothing new is required to obtain the index.
- `_class_index` (`:3065`) tolerates `project=None` by re-resolving from cwd/env.
- `ClassRefError` is already imported at `dispatch.py:40` and already handled at `:3140`/`:3149`.
- The `render_data` call sites are exactly: `preview._scene_geometry:1446` (`.get`, must stay a
  `.get`), `render_brushes_pgm:1622` and `render_quad_pgm:1868` (both `render_data or {}` — under the
  new type that yields a bare `dict` with no `.points`), `render_quad_pgm:1869`, `render_brush_pgm:1563`,
  `dispatch._world_aabb:618` (reached by `_point_pane_region` and `_resolve_zoom`), plus
  `tests/test_preview.py` and the two harness namespaces above.
- `_scene_geometry` emits an edge for **every** face regardless of facing, and `render_brushes_pgm`
  draws them with no depth test — which is why S2 needs the `flat` edge rule.

---

## 3. Slices

### S1 — `texframe.py`: one home for the shared geometry helpers

Pure move. No user-visible change, no new behaviour, no new test beyond the import-hygiene one.

**Done when**

- `uedcli/texframe.py` exists holding `world_uv_frame`, `tex_basis_default`, `newell`,
  `poly_flags_int`, and **imports nothing but stdlib, `uedcli.model` and `uedcli.builders`** — a test
  asserts this by name, and specifically that it does **not** import `preview_native` or `utexture`
  (§1's resolver-free invariant is what this guards; an earlier draft justified the test by the
  no-cargo constraint, which it does not guard at all).
- `preview._face_normal` and `preview_native._newell` are **deleted**, not aliased, and all six
  importers listed in §1 are re-pointed in this same commit.
- `bin/test` is green with **no new skips** and the same pass count as the re-measured baseline
  (this slice adds one test).
- `architecture.md`'s "Preview internals" names `texframe.py` as the shared home.

### S2 — the seam, the flag, and `flat` complete

The largest slice. It ships a usable mode, so the flag arrives with something behind it rather than
as a stub (which "no back-compat cruft" would forbid).

**The seam** becomes `PreviewData(points, faces: FaceData | None)` with
`FaceData(movers: frozenset[str], textures: TextureData | None)`. `faces` is `None` only under
`wire`; under `flat` it carries `movers` with `textures=None`. **The split is load-bearing** — a
single texture-named payload would tempt `None` for `flat`, which drops the mover set and makes the
cull treat a `CsgOper=CSG_Subtract` mover as a subtraction (spec §6).

**The mode itself** must reach `preview.py` as an explicit `faces=` parameter on all four entry
points: it cannot be inferred from the seam, since `faces=None` would be both `wire` and `flat`.
Read it in dispatch as `getattr(args, "faces", "wire")` — the harness namespaces do not carry it.

**Done when**

- `--faces {wire,flat,textured}` parses on `actor`, `stash` and `prefab preview`; `textured` is
  accepted by the parser and **rejected at dispatch with a clean exit 2 saying it lands in S4**.
  *(This is the one place a temporary refusal is right: the alternative is shipping a flag value that
  renders a wrong picture. It is deleted in S4, not kept.)*
- **`--faces wire` output is byte-identical to the pre-slice render** for a fixed scene — the primary
  regression guard for the whole feature.
- `flat` fills every face of a non-subtract brush and only the far faces of a subtract; a mover
  carrying `CsgOper=CSG_Subtract` is **not** culled; an add brush inside a subtracted room is visible.
- Mover-ness comes from `movers.is_mover` via `_mover_index`, **not** from `classify_brush`'s name
  guess — and `classify_brush`'s mover arm is replaced by the same predicate for `flat`'s fill colour,
  so one render never uses two mover predicates.
- A `CEDoor`-style mover with `CsgOper=CSG_Subtract` renders all faces **and** in mover colour.
- Exit 2, naming every offending actor, when: mover-ness cannot be resolved (all four
  `movers.is_mover` causes, distinguishable in the message); or a **mirrored** brush is present
  (`M is not None and det(M) < 0`) — and an unscaled brush does **not** crash that predicate.
- Non-mirroring scaled and sheared brushes still render under `flat`.
- Under `flat` the edge pass draws only edges of faces that survived the cull and are front-facing
  for their brush's cull sense; a culled face draws no edge, no `--highlight` outline and no on-face
  index decal, and is excluded from `occluders`.
- `flat`'s decal opacity differs from `wire`'s exactly where a culled face left `occluders` — pinned,
  because it is the sole observable of that rule.
- A **concave** face fills only inside its boundary (even-odd scanline, not a triangle fan).
- Two overlapping brushes: the nearer face wins per pixel; a coplanar tie goes to scene order.
- `PF_Invisible` faces (actor-OR'd) neither fill nor write depth nor draw line art.
- Depth buffers are `array("f")`, not `list[float]`; a `MemoryError` at an absurd `--size` is caught
  and reported as exit 2 naming the size.
- `--faces textured --brush-colors csg` exits 2; bare `--faces textured`… is S4's, but bare
  `--faces flat --brush-colors legend` works and fills from the per-actor tint.
- `--layout quad` and `--layout breakdown` both render under `flat`.
- The three corrected `help=` strings are in place, including `--show`'s "schema-free (no class
  lookup)" tail scoped to `wire`.
- `docs/usage.md` documents `--faces` and its `wire`/`flat` values.

### S3 — `--focus` over filled modes

**Done when**

- Two passes with **separate** depth buffers: context resolved opaquely into a scratch buffer
  initialised to `BG`, composited **once**; the focused brush drawn after, never occluded by context.
- A focused brush fully enclosed by another brush is visible.
- The composite is **order-independent** — a test that shuffles actor order produces identical bytes.
- **The dim constant is chosen from a real before/after render, not from arithmetic** (owner decision
  2.12). The build produces that image, picks the value, and records both the value and the image in
  `rationale/preview.md`. Starting point ≈ 0.35; the previously-proposed `_DIM_ALPHA = 0.15` was
  measured to leave a mid-grey texel ~14 levels from `BG` and is almost certainly too faint.
- The chosen constant is pinned by a test, so it cannot drift unexamined.

### S4 — `textured` — **GATED on the decoder item's S2b**

Do not start until that item has landed and its accessor exists.

**Done when**

- The S2 refusal for `--faces textured` is **deleted** (not left as a branch).
- UV per vertex from `texframe.world_uv_frame`; `u = (P − base_w)·tu_w + pan`, scale carried in the
  axis magnitude.
- **Mip level from the face's own screen-space UV gradients**, `max(hypot(du_dx,du_dy),
  hypot(dv_dx,dv_dy))` — not from any view-global projection gain. A test asserts the level-selection
  function directly at a **non-default `--iso-angle` (80°)**, where the wrong derivation differs by
  ~7×; asserting only "iso differs from ortho" proves nothing.
- **Mip level L samples the same world point as level 0** — the `/2**level` rescale. A test of level
  *selection* alone passes the buggy version.
- Texel fetch is nearest-neighbour with Euclidean wrap; a masked face's index-0 texels leave `BG`
  **and skip the depth write**; an unmasked face's index-0 texels draw normally.
- The masking gate is `(poly.flags | actor PolyFlags) & 0x2` **OR** the decoder's `bMasked`, read off
  the typed result — there is no separate predicate.
- A brush with actor-level `PolyFlags=2` masks even though its polys carry no flag.
- A synthesized fixture carrying `bMasked` exercises the texture-side arm (the decoder item's S2b
  adds the `bmasked=` fixture parameter; this slice consumes it).
- Scaled or sheared brushes exit 2 under `textured`, listing every offender.
- A non-finite UV frame exits 2 naming the actor and poly — never a `DEFAULT_GREY` fallback, which
  would be pixel-identical to a legitimately untextured face.
- A poly with no `Texture` renders `DEFAULT_GREY × shade`.
- Unreadable/bare/undecodable refs exit 2 listing **every** such ref with its case, and a bare ref's
  message says to qualify it as `Package.Name`.
- A scene referencing **no** texture renders with no texture source at all (decision 2.6's literal
  "needs"); the class index is still required, per 2.13.
- A golden PNG of a textured cube.
- **A real fill measurement is taken and recorded** before any doc states a cost number — §7 of the
  spec deliberately refuses to extrapolate its wireframe timing.

### S5 — docs, rationale, board, spec deletion

**Done when**

- `docs/usage.md` and `docs/leveldesign/general/textures-and-surfaces.md` describe all three modes,
  what each is for, and the game-content requirement of `flat`/`textured`.
- `architecture.md` "Preview internals" describes the seam, the cull, the rasterizer and `texframe`.
- `rationale/preview.md` carries the agent-side choices with *Why it is this way* / *Rejected* /
  *Refs*: even-odd scanline over a fan, `array("f")` buffers, the two-buffer focus, the chosen dim
  constant and its render.
- **The owner's rulings have a durable home before the spec is deleted.** They are parked on
  `board/inbox.md` as one `[OWNER — confirm]` item; **this slice does not write `direction/`** — that
  needs the owner's explicit yes and a `Confirmed:` trailer.
- The spec file is deleted, and `to-build.md`'s entry removed.

---

## 4. Risks

| risk | mitigation |
|---|---|
| The `render_data` reshape breaks a caller not in §1's list | §1's list was verified complete by grep across `uedcli/` and the committed harnesses; S2's Done-when includes the byte-identical `wire` guard, which fails loudly if any pane path regressed |
| `flat` requires the class index, so a no-game-install user loses a mode they had | ruled by the owner (2.13) with its cost stated; `wire` is unchanged and is the default |
| The mip rule is re-derived from a view-global gain | two earlier drafts did exactly this and both were measured wrong; S4's Done-when tests at 80° specifically, where the wrong derivation is ~7× off |
| Pure-Python fill is too slow to be usable | unknown until measured — S4 takes a real measurement. Owner has ruled no cost ceiling (2.4), so the mitigation is information, not a guard |
| A slice lands with the previous slice's refusal branch left in | S4's first Done-when is the deletion of S2's refusal |

## 5. Not in this plan

The Rust port and making the native extension non-optional; bilinear filtering; real lighting; mesh
rendering for point actors; the `Translucent` polyflag; supporting scaled/sheared brushes under
`textured`; and any change to `level preview --native` (its concave-fan defect is filed separately on
`board/inbox.md`).
