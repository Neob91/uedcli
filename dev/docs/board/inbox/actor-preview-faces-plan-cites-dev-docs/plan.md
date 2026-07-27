# Plan — `actor preview --faces {wire,flat,textured}`

Implements board item `four-actor-preview-faces-rulings-need-a-durable`
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

**Owner decision 2.11: the texture-decoder item builds FIRST, then all of this.** `board/to-build/`'s
*Native texture decode* delivers, in its slice **S2b**, the mip-pyramid accessor and the `bMasked`
flag on its typed result. **Implement the ordering as ruled: do not start S1 until that item has
landed.**

*Recorded for the owner, not acted on:* only **S4** has a technical dependency on it. S1–S3 touch no
texture code at all — `flat` reads no textures — so they could in principle land earlier or in
parallel. That is an observation, not a licence to reorder; if the sequencing should change, that is
the owner's call and is parked on `board/inbox/`.

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

1. **`rotation.actor_linear` returns `None` as the identity sentinel** (grep `IDENTITY sentinel` — it
   appears twice in `rotation.py`, for `actor_matrix` and `actor_linear`; the second is this one). The
   mirror predicate is `M = actor_linear(actor); mirrored = M is not None and det(M) < 0`. A bare
   `det(actor_linear(actor)) < 0` raises `TypeError` on nearly every brush.
2. **`getattr(args, "brush_colors", "csg")` does NOT fire for an existing-but-`None` attribute.**
   Switching the parser to `default=None` therefore needs an explicit `or "csg"` at each of the three
   consumers (grep `brush_colors` in `dispatch.py`), or `None` propagates into `_scene_geometry`,
   whose `brush_colors == "legend"` test then silently falls through to the CSG branch.

**Cite by GREP, not by line, for anything outside this plan.** Two other sessions are active; while
this plan was being written `cli.py` grew ~46 lines under one of them and every line number in an
earlier draft went stale. Line numbers appear below only where they were re-verified at the moment of
writing, and even those are backed by grep text.

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
| `uedcli/tests/test_preview_native.py` | **S1** | `_world_uv_frame`/`_tex_basis` uses (grep `_world_uv_frame`); re-point |
| `uedcli/tests/test_preview.py` | **S2** | constructs `render_data` dicts directly; migrates with the seam |
| **SEVEN committed spike harnesses** | **S1** | `dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/{analyze,verify_pan,guards,verify_model}.py` import **both** symbols (two statements each), and `dev/docs/spikes/2026-07-26-poly-rotate-curved-track/{poly_rotate,run_align,shear_align}.py` import `_world_uv_frame`. **Eleven import statements in total.** `rules/spikes.md` makes a committed harness durable evidence, and no test imports them — so `bin/test` stays green while every one of them raises `ImportError`. Re-point all eleven in the same commit; a re-export alias is forbidden. **Two PROSE references go stale too** and are in scope: `2026-07-26-unrealed-texalign-semantics/README.md` (grep `preview_native._world_uv_frame`) and `2026-07-26-poly-rotate-curved-track/uv_preview.py`'s docstring (grep `preview._face_normal`) — the §4 grep is `*.py`-and-imports-scoped and catches neither |
| `uedcli/preview.py` | **S2** | the `PreviewData` seam; the `faces=` parameter on `render_brush_pgm`, `render_brushes_pgm`, `render_quad_pgm`; the scanline fill; the depth buffer; the CSG cull; the `flat` edge rule |
| `uedcli/dispatch.py` | **S2** | `_preview_render_data` restructured (its `return {}` early exit (grep `return {}` — `:1042` at time of writing) makes the new work unreachable); mover-ness resolved here via the existing `_mover_index`; `faces=` threaded through `_render_breakdown_grid`'s `_pane` |
| `uedcli/cli.py` | **S2** | `--faces` added to `_preview_opts` (grep `def _preview_opts` — it is defined ONCE and called from three parsers, so the flag lands in one place); `--brush-colors` gains `default=None` (grep `"--brush-colors"`); the `--brush-colors`, `--focus` and `--show` help strings corrected (grep each flag name) |
| `uedcli/tests/test_actor_preview.py` | **S2** | `_prev` (grep `def _prev`) builds a `SimpleNamespace` with no `faces` attribute. **It is not broken by this change** — `_prev` takes `**kw`, so `_prev(proj, out, faces="flat")` already works, and `getattr(args, "faces", "wire")` covers the default. **The real reason it is listed is S4**: its hardcoded `brush_colors="csg"` becomes an EXPLICIT value under `default=None` and so collides with `textured` (decision 2.7). Touch it in S2 only if a new test needs it; the collision is S4's |
| `dev/docs/spikes/2026-07-24-corpus-brush-idioms/render_brushes.py` | **S2** | calls `dispatch._render_actors_to_out` with a hand-built namespace (grep `_args_for`). **The `getattr` default covers its missing `faces`, so it does not break** — it is listed so a builder checking harness callers finds it already accounted for, and because it is the natural place to smoke-test the new seam against real corpus brushes |
| `uedcli/preview.py` | **S3** | the `--focus` two-pass and its composite |
| `uedcli/preview.py`, `uedcli/dispatch.py` | **S4** | the texel path: UV per vertex, mip pick, masking gate, the texture payload on the seam |

**New**

| file | what |
|---|---|
| `uedcli/texframe.py` | shared home for `world_uv_frame`, `tex_basis_default`, `newell`, `poly_flags_int` — stdlib + `uedcli.rotation` + `uedcli.builders` only (S1) |
| `uedcli/tests/test_preview_faces.py` | the `--faces` behaviour tests (S2–S4) |
| `dev/docs/rationale/preview.md` | the agent-side choices. **Created in S3** (it must hold the dim constant that slice chooses); S5 completes it |
| `dev/docs/spikes/2026-07-27-preview-focus-dim/` | the committed before/after render decision 2.12 requires as evidence, plus the one-line harness that produced it |

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
  new type that yields a bare `dict` with no `.points`), `render_quad_pgm:1870`, `render_brush_pgm:1563`,
  `dispatch._world_aabb` (def `:609`, the `render_data` use at `:622`) (reached by `_point_pane_region` and `_resolve_zoom`), plus
  `tests/test_preview.py` and the two harness namespaces above.
- `_scene_geometry` emits an edge for **every** face regardless of facing, and `render_brushes_pgm`
  draws them with no depth test — which is why S2 needs the `flat` edge rule.

---

## 3. Slices

### S1 — `texframe.py`: one home for the shared geometry helpers

Pure move. No user-visible change, no new behaviour, no new test beyond the import-hygiene one.

**Done when**

- `uedcli/texframe.py` exists holding `world_uv_frame`, `tex_basis_default`, `newell`,
  `poly_flags_int`, and **imports nothing but stdlib, `uedcli.rotation` and `uedcli.builders`** — a
  test asserts this by name, and specifically that it does **not** import `preview_native` or
  `utexture`. **`rotation` is required, not optional**: `world_uv_frame` calls `actor_prepivot`,
  `actor_matrix` and `matvec` from it. (An earlier draft of this plan said `uedcli.model`, which none
  of the four functions touches — they are duck-typed over `actor`/`poly`. Do **not** "fix" the
  failing test by threading the matrices in as parameters: `world_uv_frame`'s signature is what keeps
  this tier and `--native` from drifting.) The graph is acyclic: `rotation` imports `.emit` only, and
  `builders` imports `.emit`/`.geometry`/`.model`/`.profile` — none reaches `preview` or `texframe`
  (§1's resolver-free invariant is what this guards; an earlier draft justified the test by the
  no-cargo constraint, which it does not guard at all).
- `preview._face_normal` and `preview_native._newell` are **deleted**, not aliased, and **every
  importer in §1's S1 rows is re-pointed in the same commit — the six modules AND the eleven
  statements across the seven spike harnesses.** No spike file is collected (`pytest.ini` sets
  `testpaths = uedcli`), so a green `bin/test` proves nothing about them: verify with the §4 grep and
  by importing each harness.
- The three `world_uv_frame` tests are **re-homed out of** `test_preview_native.py`'s module-level
  `pytest.importorskip("uedcli_native")` into an ungated module. `texframe` is pure stdlib, and left
  where they are they skip on exactly the no-cargo machine `--faces` must work on. **The zero/missing
  axis `_tex_basis_default` fallback gains its own pin** in the same move — spec §4.2 makes preserving
  it verbatim the anti-drift guarantee against `--native`, and that is its only coverage.
- `bin/test` is green with **no new skips**, and the pass count is the re-measured baseline **+1**
  (this slice adds exactly the import-hygiene test and changes no behaviour).
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

- **`--faces {wire,flat}`** parses on `actor`, `stash` and `prefab preview`. **`textured` is NOT a
  choice yet — S4 adds it to `choices`.** argparse then gives an unknown value a clean exit 2 naming
  it, with **no refusal branch to write and none to remember to delete**. *(An earlier draft shipped
  `textured` in `choices` and refused it at dispatch; that is a flag value whose entire behaviour is
  an error message — the shim shape `CLAUDE.md` forbids — and it would have made `-h` advertise a
  mode `docs/usage.md` simultaneously denied. Growing `choices` in S4 keeps help, docs and behaviour
  consistent at every commit.)*
- **`--faces wire` output is byte-identical to the pre-slice render** for a fixed scene — the primary
  regression guard for the whole feature. **Capture the golden FIRST**, from the tree *before* any S2
  code lands, and commit it in the same slice; a golden generated after the rewrite pins the rewrite,
  not the behaviour. **S3 and S4 both re-assert it** — each touches `preview.py`/`dispatch.py` again,
  and `wire` shares the `--focus` path S3 restructures, so without a restatement the guard lapses
  after S2.
- `flat` fills every face of a non-subtract brush and only the far faces of a subtract; a mover
  carrying `CsgOper=CSG_Subtract` is **not** culled; an add brush inside a subtracted room is visible.
- Mover-ness comes from `movers.is_mover` via `_mover_index`, **not** from `classify_brush`'s name
  guess — and `classify_brush`'s mover arm is replaced by that predicate **everywhere its answer is
  consumed in a filled render**, so one render never uses two mover predicates. That is the fill
  colour AND **`is_solid`** (`preview.py`, grep `is_solid = classify_brush`), which feeds `occluders`
  and so decal grading; mis-graded decals is one of the two symptoms spec §4.7 names, so leaving
  `is_solid` on the name guess would satisfy a narrow reading and violate the spec.
- A `CEDoor`-style mover with `CsgOper=CSG_Subtract` renders all faces **and** in mover colour.
- *(Test seam: `uedcli/tests/conftest.py` autouse-stubs `dispatch._mover_index` with a
  `StubClassIndex` for every test, with a `@pytest.mark.real_mover_index` opt-out — grep
  `real_mover_index`. The stub models all four failure causes; drive it rather than fight it.)*
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
- `--faces flat --brush-colors legend` fills from the per-actor tint; with no `--brush-colors` it
  fills from the CSG palette.
- **The `default=None` + `or "csg"` plumbing is asserted AT THE SEAM, not by picture.** `brush_colors`
  is compared in exactly one place (`preview.py`, grep `brush_colors == "legend"`), so `None` and
  `"csg"` are behaviourally identical through everything S2 renders — a picture test passes with the
  `or "csg"` fixes entirely absent. Assert instead that **each of the three `dispatch.py` consumers
  hands `preview` a non-`None` value** when the flag is defaulted. Without this, a missed fixup ships
  silently through S2 and S3 and first appears at S4 as a wrong `--layout breakdown` render.
- `--layout quad` and `--layout breakdown` both render under `flat`.
- **`--faces flat --focus X` is explicitly OUT of scope here and must not be left half-working.**
  Focus today dims *edges only* (`preview.py`, grep `edge_alpha`), which over opaque fills gives the
  near-invisible, order-dependent picture spec §4.8 refutes. Until S3, that combination **exits 2
  saying filled-mode focus lands in S3** — a refusal, not a wrong picture. S3's first Done-when
  removes it. *(The one temporary refusal in this plan: unlike a stub flag value it guards a real
  interaction rather than standing in for an unimplemented mode.)*
- **A `nonsolid` sheet — a single face — renders from BOTH sides**, since the cull is subtract-only.
  "Fills every face of a non-subtract brush" does not pin the from-behind case, which is the one the
  cull could silently break.
- **Point sprites and each `--show` overlay survive an opaque fill** — the fills-at-step-2 ordering.
- **`flat` fill RGB on the legacy `color_by_csg=False` path** (`render_brushes_pgm`'s default, which
  the existing suite drives constantly) — the third of spec §4.5's three colour cases.
- **`wire` still renders when the class hierarchy cannot load**, alongside the failing arm above —
  decision 2.13's cost in both directions, and the promise §0 makes about `wire`.
- **`prefab preview --prefab-dir X --faces flat` SUCCEEDS from inside a project** — `--prefab-dir`
  overrides only the prefab library root; it implies neither "no project" nor "no resolver".
- **Point sprites and each `--show` overlay survive an opaque fill** — the fills-at-step-2 ordering.
  Placing them later paints over every sprite and overlay, which is why the order is specified.
- **`flat` fill RGB on the legacy `color_by_csg=False` path** (`render_brushes_pgm`'s default, which
  the existing suite drives constantly) — the third of §4.5's three colour cases.
- **`wire` still renders when the class hierarchy cannot load**, alongside the failing arm above —
  decision 2.13's accepted cost in both directions, and the promise §0 makes about `wire`.
- **`prefab preview --prefab-dir X --faces flat` SUCCEEDS from inside a project** — `--prefab-dir`
  overrides only the prefab library root; it does not imply "no project", and no project does not
  imply no resolver.
- The three corrected `help=` strings are in place, including `--show`'s "schema-free (no class
  lookup)" tail scoped to `wire`.
- `docs/usage.md` documents `--faces` and its `wire`/`flat` values, **and its wireframe-only wordings
  are corrected in this slice** — grep it for `the wireframe viewer`, `color wireframe`,
  `The wireframe is coloured by CSG op`, `the wireframe's colour source`, the `actor preview` synopsis
  block, and `stash preview`'s `composite wireframe`. Each becomes false the moment `flat` ships.

### S3 — `--focus` over filled modes

**Done when**

- **The S2 refusal of `--faces flat --focus` is removed**, and that combination renders.
- **`--faces wire` is still byte-identical to S2's committed golden** — `wire` uses the `--focus`
  path this slice restructures.
- **`docs/usage.md`'s `--focus` description is corrected in THIS slice** — it says other brushes
  "recede to a faint (dimmed) **wireframe**", which this slice falsifies. §0b requires docs to move
  with the slice that changes behaviour; S5 is the cross-cutting sweep, not a dumping ground.
- Two passes with **separate** depth buffers: context resolved opaquely into a scratch buffer
  initialised to `BG`, composited **once**; the focused brush drawn after, never occluded by context.
- A focused brush fully enclosed by another brush is visible.
- The context composite is applied **once per pixel**, not once per face — assert it on a scene where
  several non-focused faces overlap, checking the result equals a single blend of the resolved buffer.
  **Do NOT assert this by shuffling actor order:** `assign_tints` is documented as *"cycled by scene
  position"* and spec §4.7 fixes the coplanar tie-break to scene order, so a shuffle legitimately
  changes the bytes. What must be order-independent is the blend, not the scene.
- **The dim constant is chosen from a real before/after render, not from arithmetic** (owner decision
  2.12). The image **is** the evidence, so it needs a committed home: `_scratch/` is gitignored, so
  the before/after pair and the harness that made it are committed under
  `dev/docs/spikes/2026-07-27-preview-focus-dim/` (the tree's existing pattern for durable evidence),
  and `rationale/preview.md` — **created in this slice** — records the chosen value and cites that
  directory. Starting point ≈ 0.35; the previously-proposed `_DIM_ALPHA = 0.15` was measured to leave
  a mid-grey texel ~14 levels from `BG` and is almost certainly too faint.
- The chosen constant is pinned by a test, so it cannot drift unexamined.

### S4 — `textured` — **GATED on the decoder item's S2b**

Do not start until that item has landed and its accessor exists.

**Done when**

- **`textured` is added to `--faces`'s `choices`**, and `docs/usage.md` gains it in the same commit,
  so help and docs never disagree.
- **`--faces wire` is still byte-identical to S2's committed golden.**
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
- **`--faces textured --brush-colors csg` exits 2, and bare `--faces textured` succeeds** — the
  `default=None` + `or "csg"` mechanism, in the one slice where the pairing is meaningful. Check all
  three consumers: a missing `or "csg"` at the breakdown call site puts `None` into `_scene_geometry`,
  whose `legend` test falls through silently — a wrong picture under `--layout breakdown` only.
- Scaled or sheared brushes exit 2 under `textured`, listing every offender.
- A non-finite UV frame exits 2 naming the actor and poly — never a `DEFAULT_GREY` fallback, which
  would be pixel-identical to a legitimately untextured face.
- A poly with no `Texture` renders `DEFAULT_GREY × shade`.
- Unreadable/bare/undecodable refs exit 2 listing **every** such ref with its case, and a bare ref's
  message says to qualify it as `Package.Name`.
- A scene referencing **no** texture renders with no texture source at all (decision 2.6's literal
  "needs"); the class index is still required, per 2.13.
- **`textured` emits no wireframe pixels and `flat` does** — decision 2.5's most visible observable.
- **§4.1's shade formula and its truncation** asserted on a known normal, separately from the golden:
  a golden cannot tell a shade error from a UV error.
- Each of the resolver's **three `None` causes** produces a distinct exit-2 message naming that cause.
- `--layout quad` and `--layout breakdown` both render under **`textured`**.
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
  `board/inbox/` as one `[OWNER — confirm]` item; **this slice does not write `direction/`** — that
  needs the owner's explicit yes and a `Confirmed:` trailer.
- The spec file is deleted, and `board/to-build/`'s entry removed.

---

## 4. Risks

| risk | mitigation |
|---|---|
| The `render_data` reshape breaks a caller not in §1's list | S2's Done-when includes the byte-identical `wire` guard. **Do not trust the list — re-run the grep.** A first draft of this plan asserted the list was complete and had missed seven committed spike harnesses; the tree also gains files under concurrent sessions. The command is `git ls-files '*.py' \| xargs grep -ln '_face_normal\|_world_uv_frame\|render_data'` |
| `flat` requires the class index, so a no-game-install user loses a mode they had | ruled by the owner (2.13) with its cost stated; `wire` is unchanged and is the default |
| The mip rule is re-derived from a view-global gain | two earlier drafts did exactly this and both were measured wrong; S4's Done-when tests at 80° specifically, where the wrong derivation is ~7× off |
| Pure-Python fill is too slow to be usable | unknown until measured — S4 takes a real measurement. Owner has ruled no cost ceiling (2.4), so the mitigation is information, not a guard |
| A slice grows `--faces`'s `choices` without the matching docs | S4's first two Done-whens pair the `choices` change with `docs/usage.md` in the same commit, so `-h` and the docs never disagree |
| A temporary refusal is left behind | There is exactly ONE in the plan — S2 refusing `--faces flat --focus` — and removing it is **S3's first Done-when**. `textured` is absent from `choices` rather than refused, so it leaves no branch at all |

## 5. Not in this plan

The Rust port and making the native extension non-optional; bilinear filtering; real lighting; mesh
rendering for point actors; the `Translucent` polyflag; supporting scaled/sheared brushes under
`textured`; and any change to `level preview --native` (its concave-fan defect is filed separately on
`board/inbox/`).
