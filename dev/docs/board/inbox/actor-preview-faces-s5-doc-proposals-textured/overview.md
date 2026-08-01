+++
priority = "p2"
kind = "owner-question"
summary = "[OWNER — confirm] exact S5 doc text for actor preview --faces textured: rationale, architecture, direction cross-ref, one leveldesign line."
depends-on = ["actor-preview-faces", "four-actor-preview-faces-rulings-need-a-durable"]
+++

# [OWNER — confirm] actor-preview-faces S5 doc proposals (textured)

`actor preview --faces textured` (S4) shipped to master (commit `de04a72`). `docs/usage.md` was
updated in that commit and is **not** re-proposed here. S5's remaining doc edits all touch
owner-approval-gated trees (`dev/docs/*`, `docs/leveldesign/`), so nothing below is applied — this
item holds the exact proposed text for a yes.

**How to answer:** one yes covers all four sections, or approve/edit each. Where the answer is a
`direction/` confirm, that is a separate parked item (see section C) and is confirmed there, not here.

The two pure board-mechanics tail items and the still-owed measurement are listed at the end — the
owner need not draft anything for those.

---

## A. `dev/docs/rationale/preview.md` — ADD one section (engineering choices behind `textured`)

The file already holds two sections (the focus pass, the dim constant). Add the section below at the
end. It records only the **engineering**; the product rulings (refuse-not-placeholder, the
game-content cost, "needs" is literal) are the owner's and live in section C's `direction/` item.

**BEFORE** — the file ends after the dim-constant section's `**Refs.**` line.

**AFTER** — append:

> ## `textured` — the texel path over the SAME cull and depth buffer
>
> `textured` reuses `flat`'s cull, `array("f")` depth buffer and occlusion test unchanged; only the
> fill differs — each pixel samples the face's decoded texture through its authored UV frame instead
> of one flat hue (`_fill_face_textured`).
>
> **Why it is this way.**
>
> - **UV is affine in screen space, solved once per face — no per-pixel perspective divide.** Under
>   the orthographic preview camera `u(P) = dot(P − base_w, tu_w) + pan` is affine in world `P`, so it
>   solves from the SAME three plane probes the depth map already uses (`_face_uv_affine` shares
>   `_plane_screen_probes` with `_face_depth_affine`). One consequence pays for another: the screen
>   gradients `(au, bu)`/`(av, bv)` the UV solve produces ARE the mip term below, computed for free.
> - **The mip level is per FACE, from that face's own screen-space UV gradients**
>   (`_mip_level` = `log2(max(hypot(du_dx,du_dy), hypot(dv_dx,dv_dy)))`, clamped to the pyramid). A
>   single view-global projection gain understates the rate on an oblique wall — ~1.7× at the default
>   iso angle, unbounded near edge-on — and would alias exactly the grazing surfaces a texture check
>   most needs to read.
> - **Nearest-neighbour with Euclidean wrap** (`int` `%` on the mip's `w`/`h`). Matches `render.rs`;
>   no filtering, so a texel edge is a texel edge in the preview.
> - **A masked hole writes neither colour NOR depth.** When the face is masked and the sampled texel's
>   `mask == 0`, the pixel is skipped entirely, so a face BEHIND the hole shows through; an unmasked
>   face draws palette index 0 as an ordinary colour. The masked answer is resolved in dispatch as
>   `(poly.flags | actor PolyFlags) & PF_Masked` **OR** the decoder's `bMasked`, off the typed result —
>   one gate, no separate predicate.
> - **Shade matches the native tier.** `_face_shade` = `0.55 + 0.45·|N·L|/|N|` on the world Newell
>   normal, and the colour is `min(int(texel·shade), 255)` per channel — byte-for-byte `render.rs`'s
>   key light and truncation, so `--native` and this tier agree up to f32-vs-f64 (spec §4.9). A face
>   `render.rs` also skips (< 3 vertices, zero-length normal) shades `None` and is dropped.
>
> **Rejected.**
>
> - **A view-global projection gain for the mip** — two earlier drafts of the feature derived it this
>   way and both were measured wrong; the per-face gradient is the correction, tested at a non-default
>   `--iso-angle` where the wrong derivation is ~7× off.
> - **`DEFAULT_GREY` as a fallback for a texture the render cannot produce** — a non-finite UV frame,
>   or an unreadable/bare/undecodable ref. Grey is pixel-identical to a legitimately untextured face
>   (`tex_index < 0`), so a fallback would hide the very defect this mode exists to surface. Each such
>   case is a clean exit 2 naming the actor/poly or listing every offending ref (a bare ref says to
>   qualify it `Package.Name`); a missing resolver names which of its three causes applies; a scene
>   that references NO texture renders with no texture source at all (the owner's literal "needs").
>   The refusals themselves are the owner's product ruling — see the `direction/` item below — recorded
>   here only for the engineering reason grey cannot stand in.
> - **Bilinear filtering, and scaled/sheared brushes under `textured`** — both deferred (plan §5). A
>   scaled or sheared brush exits 2 listing every offender, because its geometry is built with the full
>   linear transform while the UV frame uses rotation only, so the texture would not follow the
>   geometry — a wrong answer in the one tool meant to be authoritative about UV.
>
> **Refs.** `uedcli/preview.py` `_fill_face_textured`, `_face_uv_affine`, `_mip_level`, `_face_shade`,
> `_plane_screen_probes`, `DEFAULT_GREY`; `uedcli/cli/rendering.py` `preview_textures`,
> `_reject_transformed_brushes`, `_reject_explicit_brush_colors`, `_texture_resolver_cause`;
> `uedcli/tests/test_preview_faces.py` and the golden `tests/fixtures/preview_textured_golden_iso.png`.

---

## B. `dev/docs/architecture.md` — "Preview internals": name `textured`

The section names the modes as `**--faces {wire,flat}**` and describes `wire`/`flat` in bullets. Two
minimal edits.

**B1 — the heading paragraph.**

BEFORE:

> **`--faces {wire,flat}`** picks whether faces are also FILLED. It is an explicit `faces=` parameter on
> `render_brush_pgm`/`render_brushes_pgm`/`render_quad_pgm` and on `_render_breakdown_grid`'s `_pane` —
> it cannot be inferred from the seam, since `PreviewData.faces is None` would mean both `wire` and a
> filled mode.

AFTER (only `{wire,flat}` → `{wire,flat,textured}`):

> **`--faces {wire,flat,textured}`** picks whether faces are also FILLED. It is an explicit `faces=`
> parameter on `render_brush_pgm`/`render_brushes_pgm`/`render_quad_pgm` and on
> `_render_breakdown_grid`'s `_pane` — it cannot be inferred from the seam, since
> `PreviewData.faces is None` would mean both `wire` and a filled mode.

**B2 — add a `textured` bullet** immediately after the existing `**flat**` bullet (the one ending
"…so no sprite or `--show` overlay is painted over."):

> - **`textured`** fills each surviving face by sampling its OWN decoded texture through its authored UV
>   frame instead of a flat hue (`_fill_face_textured`), reusing `flat`'s cull, depth buffer and
>   occlusion test unchanged. UV is affine in screen space, solved once per face off the same plane
>   probes as depth (`_face_uv_affine`/`_plane_screen_probes`); the mip level is per face from that
>   face's own screen-space UV gradients (`_mip_level`), never a view-global gain; the fetch is
>   nearest-neighbour with wrap; and a masked face's index-0 texels write neither colour nor depth
>   (`(poly.flags | actor PolyFlags) & PF_Masked` OR the decoder's `bMasked`). Colour is `texel·shade`
>   truncated as `render.rs`'s key light (`_face_shade` = `0.55 + 0.45·|N·L|/|N|`), so it agrees with
>   `--native` up to f32-vs-f64. **`textured` emits NO wireframe** (a highlighted face takes only an
>   outline); a poly with no `Texture` fills `DEFAULT_GREY·shade`. Its resolution and refusals live in
>   dispatch (`cli/rendering.py` `preview_textures`): a scaled or sheared brush, `--brush-colors` given
>   with `textured`, a non-finite UV frame, and any unreadable/bare/undecodable ref each exit 2 naming
>   the offender (a bare ref says to qualify it `Package.Name`); no resolver names which of three causes
>   applies; a scene referencing NO texture needs — and resolves — none. **Accepted cost, as `flat`:
>   `textured` needs the project's game content; `wire` needs neither.**

*(No change needed to the `.faces`/`FaceData` paragraph near the end of the section — it already
carries `textures: TextureData | None` and explains why the mover set and textures are separate
fields.)*

---

## C. `dev/docs/direction/` — NO new text proposed here

The `--faces` product rulings (the three tiers, the subtract-far-faces rule, refuse-not-placeholder,
"no cost ceiling", the game-content requirement) already have a durable-home proposal parked as its
own `[OWNER — confirm]` item: **`four-actor-preview-faces-rulings-need-a-durable`** (suggested home
`direction/trunk-and-editor.md`). Its verbatim blockquote already covers `textured`, including:

> Its `--faces` modes are `wire` … `flat` … and `textured` (each face painted with its real texture
> through its authored UV frame). … **A texture the render actually needs and cannot read is a
> refusal, never a placeholder**; a scene that references no texture needs no texture source.

So there is **no existing `direction/` ruling that this S5 work amends**, and no `Confirmed:` trailer
is owed by S5's doc commits. The direction/ home is confirmed by approving that separate item, not
this one. Nothing to draft here — flagged only so the cross-reference is explicit.

---

## D. `docs/leveldesign/general/textures-and-surfaces.md` — ONE line proposed (owner-gated)

**Proposed: yes, one line — but it is tool-behaviour, not a new craft/engine claim, so it is
low-risk to approve.** The doc's "Alignment & scrolling" section already tells the user to align and
warns that alignment can look wrong after a rebuild; `--faces textured` is exactly how to SEE that
offline, which is the feature's stated purpose. Nothing about the engine or craft numbers is asserted.

Add as the first bullet under "## Alignment & scrolling":

> - **Preview alignment offline before a full build:** `actor preview <brush> --faces textured` paints
>   every face with its real texture through its authored UV frame, so a misaligned, mirrored, wrapped
>   or wrong-referenced surface is visible without a `level materialize` + render. It needs the game
>   content (like `--faces flat`); `--faces wire` shows outlines only and needs none.

**If the owner would rather keep this doc free of tool pointers, the answer is "none needed"** — the
same fact is in `docs/usage.md`, and the leveldesign doc loses nothing essential.

---

## Tail — board mechanics + the owed measurement (no owner drafting)

Once the texts above are approved and applied, S5 finishes with pure mechanics (agent-operated, no
owner draft):

- `git mv` board item `actor-preview-faces` from `to-build/` to `done/`, trimmed to a reference line.
- Delete its ephemeral `spec.md` and `plan.md` (they are the deleted-on-build spec/plan), and delete
  the standalone spec item `four-actor-preview-faces-rulings-need-a-durable` **only after** its
  `direction/` text is confirmed (section C) — not before.

Still owed, and **content-blocked**, tracked separately:

- **A real fill-cost measurement.** Plan S4's last Done-when. It needs a game corpus, which this
  container has no games config or `.u` for; `docs/usage.md` deliberately states no cost number, so
  nothing false shipped. Take it on real content before any doc states a cost. (Its own inbox item, if
  not already filed, should carry this.)
