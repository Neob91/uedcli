# The offline renderer in Rust — rasterization, text labels, and output formats

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** what should the Rust rewrite use to produce uedcli's diagram and photo renders, and what does moving off Pillow cost or buy?

## Summary

- **Neither renderer anti-aliases.** `preview.py` draws aliased Bresenham lines (`_line`) and fills
  through an integer `_px`/`_blend_px`; `render.rs` samples triangles at pixel centres with a hard
  `w0<0 || w1<0 || w2<0` reject (`raster_tri`). Every AA'd 2D crate (`tiny-skia`, `cairo-rs`,
  `vello_cpu`) is therefore the *wrong primitive*, not merely an extra dependency — matching today's
  output means turning its AA off and still re-implementing the pixel rule.
- **There is no font to port.** All text is a 42-glyph 3×5 boolean table, `_FONT` in
  `old/uedcli/preview.py:364` (`0-9 : - + . / _` + the full uppercase alphabet), nearest-upscaled by
  an integer `scale`. The only real font anywhere is Pillow's bundled Aileron, used for
  `--layout breakdown` pane captions via one bare `ImageDraw.text` call — and that is the one text
  path no golden pins.
- **The awkward part is label *placement*, not glyphs.** `actor diagram` paints a poly index flat
  *in the face's own 3-D plane* and inverse-maps each screen pixel back to a glyph texel
  (`_face_decal_basis` → `_plan_onface_texture` → `_draw_painted_decal`). No text engine does this;
  a boolean glyph grid is exactly the right input, so the current design ports almost verbatim.
- **Pillow does almost no rendering.** Nine distinct operations across the whole package
  (`open`/`save`/`new`/`frombytes`/`tobytes`/`convert`/`paste`/`crop`/`transpose`, plus that one
  `ImageDraw.Draw`). `preview.py` is stdlib-only and emits PPM/P6; Pillow enters at the write
  boundary. Replacing it is a PNG-encoder swap plus a handful of `image`-crate calls.
- **SVG can only be an addition, not a replacement**, and is not an output today. No multimodal model
  accepts SVG as an image input (Claude: JPEG/PNG/GIF/WebP only), so a vector wireframe reaches an agent
  as *text* or not at all. Grepped: no SVG in `old/uedcli/`; one dev script
  (`old/dev/scripts/readme-hero/render-synced-svg.py`) wraps rendered PNG frames as
  `<image href="data:image/png;base64,…">` — raster inside an SVG shell.
- **Today's Rust half is only the photo triangle rasterizer.** `render_frame` takes flat world-space
  polys + a texture table + a camera basis and returns RGB bytes. Every label, legend, overlay,
  gridline, locator gutter, sprite and marker lives in Python.
- **416 preview tests; 4 compare images.** Image goldens are byte-exact on *decoded* RGB (PNG is a
  container only) with a `UEDCLI_BLESS_GOLDEN` bless flow and zero tolerance. ~100 tests are
  CLI-dispatch level (differential-testable against `old/`); the other ~310 drive renderer internals
  directly and need equivalent Rust seams.
- **Rasterization is not the bottleneck in either path.** On the diagram, ~85% of a default quad is
  on-face annotation layout. On the photo, 8.0 s of an 11.5 s 8-shot batch is the CSG carve; the
  rasterizer is ~0.35 s/frame.
- Licence note: uedcli is MIT (`old/pyproject.toml`, `old/uedcli-native/Cargo.toml`). `tiny-skia` is
  BSD-3-Clause, `ab_glyph` is **Apache-2.0 only**, most others are MIT/Apache-2.0 dual.

## What we have today

Four offline raster paths, no shared rasterizer:

| Path | Code | Projection | Output |
|---|---|---|---|
| `actor`/`stash`/`prefab diagram` | `old/uedcli/preview.py` (2847), `old/uedcli/cli/rendering.py` (1014) | ortho top/front/side + synthetic iso | PPM/P6 in memory → PNG |
| `level photo` (default `--native`, `--mode lit`/`polys`) | `old/uedcli/preview_native.py` (1356) → `old/uedcli-native/src/render.rs` (1953) | perspective, SHOT grammar | RGB bytes → PNG |
| `level photo --native --mode wire` | `old/uedcli/preview_wire.py` (179) | perspective, pixel-matched to `render.rs` | PPM → PNG |
| `class preview` mesh thumbnail | `old/uedcli/meshrender.py` (355) | fixed iso | Pillow `Image` → PNG |

The GUI (`old/web/`, Three.js/WebGL) is a fifth, independent renderer fed by `old/uedcli/serve/`; out of
scope here except as a cautionary datapoint (below). Framing: `BG = 64` (`#404040`, owner ruling
2026-08-30); `--size 1024` default and **uncapped** for `diagram` (`--layout quad` is four independent
`size//2` panes, each with its own 16 px caption band and locator density); `level photo` defaults to
`1280x960` and `render_frame` rejects anything outside `1..=16384`.

## Findings

### What the renderer actually produces

| Feature | Where it lives today | Portability risk |
|---|---|---|
| Ortho projection, 4 views, `--iso-angle` | `preview.py` `_project`/`_view_depth` | low — pure arithmetic |
| Perspective projection + near clip | `render.rs` `clip_near`; `preview_wire.py` (duplicate) | low — already Rust once |
| `--layout quad`/`single`/`breakdown` | `preview.py` `render_quad_pgm`; `rendering.py` `_render_breakdown_grid` | low; breakdown stitch is the only Pillow-side layout |
| CSG wire colours (`--brush-colors csg`/`legend`) | `preview.py` `classify_brush`/`_CSG_PALETTE`/`assign_tints` | low — table lookup |
| Back-face cull + `array("f")` z-buffer fill | `preview.py` `_is_front`/`_fill_face` | low |
| Textured fill, per-face mip, masked holes | `preview.py` `_fill_face_textured`/`_mip_level`; `render.rs` `raster_tri` | **medium** — two implementations must stay byte-agreeable |
| Translucent/modulated blend, mirrors, `PF_FakeBackdrop` sky | `render.rs` only | low — pure Rust already |
| Lightmap sampling | `render.rs` + `light.rs` | low |
| `--focus` dim mask + `_fade_dimmed` | `preview.py` | low, but the once-per-pixel rule is load-bearing |
| `--highlight` bold edges, vertex/pivot glyphs, selection brackets | `preview.py` `_draw_vertex_dot`/`_draw_pivot_marker`/`_draw_selection_brackets` | low |
| On-face poly-index decals (in-plane, halo, overlap keyline) | `preview.py` ~1026–1560 (~580 LOC) | **high** — bespoke; see below |
| Locator-cell gutter (`A1`…), stderr legend, `--json` cells | `preview.py` `_draw_text`/`_draw_locator_gutter`; `rendering.py` `_preview_json` | medium — text metrics drive layout |
| World gridline lattice + per-pane caption (`--grid-size`) | `preview.py` `_grid_escalation`/`_draw_grid_backdrop` | low |
| Point-actor sprites (decoded texture blit) and diamond markers | `preview.py` `_blit`/`_filled_diamond` | low |
| `--show collision`/`light-range`/`sound-range` overlays | `preview.py` `_draw_cylinder`/`_draw_sphere` | low |
| Quad pane captions | `preview.py` `_draw_text` (3×5 font) | low |
| Breakdown pane captions | `rendering.py:329` `ImageDraw.text` (Pillow Aileron) | low — unpinned; reimplement in the 3×5 font |
| PPM→PNG encode, breakdown stitch, mesh buffer, lightmap atlas | Pillow | low — `png`/`image` crate |

Anti-aliasing: none, anywhere. `_line` is Bresenham, "visits each pixel once, so no double-blend";
`weight>1` thickens to a `weight×weight` block; `alpha<1` composites per pixel but does not vary
coverage. `_circle` is a polyline of rounded integer points. `raster_tri` is a pixel-centre
point-in-triangle test. The only blending is explicit alpha (`_blend_px`) for dimmed wires, decals
(0.7) and their halo (0.35). A live GUI bug argues for keeping it that way:
`done/ortho-grid-line-sub-pixel-antialiasing-blurry` traced "some lines render wider than others, and
when I move they alternate" to WebGL's 1-px line rasterizer splitting coverage across two pixels, fixed
only by snapping each line to a device-pixel centre — a property the offline renderer has by construction.

### The Python/Rust split today

The whole FFI render surface is one function, `render_frame` (`old/uedcli-native/src/lib.rs:832`):
`polys` (vertex ring + UV base/axes/pan + `tex_index` + `masked` + `poly_flags` + optional lightmap),
`textures` (`(w,h,rgb,mask)` mip 0), a camera **basis** (`location, forward, right, up, fov_deg`),
`size`, optional `sky` basis, `texture_use` → `width*height*3` RGB bytes.

What Rust does not do: FRotator→basis conversion ("Rust NEVER converts FRotator angles, so the camera
convention is single-sourced"), the CSG solve call, the surf→source-poly join, the UV frame
(`base_w = Location + L·(Origin − PrePivot)`, `axes_w = (L⁻¹)ᵀ·axes`), texture decode and the mip
pyramid, mover/mesh/sprite actor polys, sky-actor discovery, the shot grammar, the two-tier
`geom_hash`/`light_hash` scene cache, and PNG encode — all `preview_native.py` `build_scene`
(~1100 LOC of the file's 1356).

What `preview.py` does that `render.rs` does not: everything textual and schematic — the whole label,
legend, gutter, gridline, overlay and marker inventory above, plus the ortho projections, `--focus`,
`--highlight` and the breakdown/quad layouts. `render.rs` in exchange has translucent and modulated
blending, planar mirrors with a shared recursion cap of 3, `PF_FakeBackdrop` sky scenes and lightmap
sampling — none of which `preview.py` has. `preview_wire.py` is a deliberate third copy whose projector
and near clip "match the Rust `render_frame` EXACTLY — horizontal FOV, `focal = (w/2)/tan(fov/2)`,
`screen = (w/2 + r*focal/d, h/2 - u*focal/d)`": two pixel-identical implementations of one projector,
exactly the divergence the consolidation item exists to remove.

### Text labels

`_FONT` (`old/uedcli/preview.py:364`) is a `dict[str, list[str]]` of 42 glyphs as five 3-character
rows of `"1"`/`"0"`. Two consumers:

- **Screen-aligned** — `_draw_text` blits each `"1"` as a `scale×scale` block, 1-column gaps,
  `name_scale = max(2, size // 256)`. Used for quad pane captions, the locator gutter letters/numbers,
  and the grid caption.
- **In-plane painted** — `_text_bitmap` widens the digits into a 2-digit slot, adds a blank row and an
  underline bar (the 6-vs-9 cue), giving a 7-row boolean grid. `_face_decal_basis` builds an in-plane
  world frame anchored to world +Z projected into the face plane (an edge-anchored basis "shears to an
  italic under projection"), `_max_inscribed_box` finds the largest box that fits the projected face,
  and `_draw_painted_decal` inverse-maps every pixel of the glyph parallelogram back to a texel, then
  blends a 1-px halo and the tint. A number too small to read on screen is omitted; there is no leader
  fallback.

Font metrics are load-bearing on layout, not just looks: `_locator_label_px(chars, scale)` returns
`((4*chars − 1)*scale, 5*scale)` and feeds `_locator_gutter_px`, the auto locator density and the lattice
escalation — a proportional face would change the gutter width and the chosen cell count.

The one external font is `old/uedcli/cli/rendering.py:329`, `draw.text(…, caption, fill=(0,0,0))` with no
`font=`, so Pillow calls `ImageFont.load_default()`; with FreeType present that loads a bundled
**Aileron Regular**, which dotcolon releases as **"No Rights Reserved" / public domain**. No golden
covers `--layout breakdown`, so nothing pins those glyphs.

### Performance record

| Board item | Stage | Recorded numbers |
|---|---|---|
| `make-actor-preview-faster` | `to-spec` (spec draft, 3 open questions) | quad wire @1024: ~500–650 ms with `annotate=all`, ~90 ms with none; single iso 450/40 ms; geometry alone 31 ms @1024, 65 ms @2048; Pillow encode ~30 ms; CLI wall ~0.47 s. cProfile of 3.0 s: `_onface_candidates` 1.11, `_draw_painted_decal` 1.04, `_max_inscribed_box` 0.90, `_erode_convex` 0.81, `_clip_ge` 0.37 — "~85% of a default render is placing each poly's index number inside its face". Target ≤250 ms; NumPy rejected pending an owner call. |
| `consolidate-level-preview-native-onto-the-actor` | `to-plan` (spec + plan written) | Retire `render.rs` and `preview_native.py`'s camera half; one `preview.py` path for both verbs; "whole-level pure-Python raster is low single-digit seconds". |
| `rust-rasterizer-for-the-consolidated-offline` | `inbox` | The owner's 2026-08-05 follow-on: a Rust rasterizer for the *consolidated* `preview.py`, explicitly "a DIFFERENT Rust rasterizer from the retired `render.rs`". Depends on the consolidation landing. |
| `delete-the-dead-render-rs-rasterizer-source` | `inbox` | Post-consolidation chore. Owner: "we'll bring it back separately". Not yet actionable — `--native` is still the `level photo` default and still calls `render_frame`. |
| `actor-preview-rendering-improvements` | `to-spec` | Not perf: quad captions into a header strip (breakdown already does), translucent x-ray forked out, dashed hidden lines recommended skipped. |
| `add-visual-grid-for-2d-views-in-level-actor` | `to-plan` | A faithful `DrawGridSection` port (step doubles until ~4 px apart, every 8th strong, odd lines fade before being dropped). Shipped as `--grid-size` with a golden; the item has not been retired. |
| `remove-numbering-grid-from-level-actor-preview` | `to-plan` | Resolution reversed by a blind spike (6/6 exact with cells vs 0/6 without): keep it, rename to `--locator-cells`, add `--no-locator-cells`, draw fainter. Shipped; item not retired. |
| `native-preview-perf-an-8-shot-castle-batch` | `inbox` | 8 shots @1280×960 = 11.4–11.5 s vs a ≤10 s target; `build_geometry` 8.0 s, trunk read 0.11 s, texture decode 0.24 s, **rasterize + PNG encode ~0.35 s/frame**. "rayon rows, the spec's known lever, would buy nothing here." |
| `gui-wireframe-perf-remaining-marker-sprite-draw` | `inbox` | GUI/WebGL, not offline: ~11,000 draw calls/pane on WanChai (2287 actors, 8235 brush polys), 22,688→1,713 idle draw calls and 350→110 ms/frame after merging rings into one `LineSegments`. |
| `gui-reload-rebuild-slow-memoize-scene` | `done` | Reload/Rebuild slowness was `ClassIndex`/`ClassDefaults` rebuilt per request (~3 s), not the solve. |
| `incremental-csg-checkpointing-for-gui-rebuild` | `inbox`, unscoped | `session_rebuild` ~24 s on a real level; order-dependent CSG forces a full replay on any geometry edit. |

Read together: the rasterizer has never been the cost. The diagram's cost is a bespoke 2-D layout search
over face polygons; the photo's is CSG.

### How renders are tested

| File | Tests | Level |
|---|---|---|
| `old/uedcli/tests/test_preview.py` | 114 | renderer internals (`render_brushes_pgm` with hand-built `PreviewData`) |
| `old/uedcli/tests/test_preview_native.py` | 99 | `render_frame` + `build_scene`, incl. the one native golden |
| `old/uedcli/tests/test_actor_preview.py` | 74 | CLI dispatch (84 `dispatch.dispatch` calls) |
| `old/uedcli/tests/test_preview_faces.py` | 58 | cull/fill/texel rules + 3 goldens |
| `old/uedcli/tests/test_preview_grid.py` | 40 | gridline math + 1 golden |
| `old/uedcli/tests/test_preview_batch.py` | 23 | `--game` in-container batch |
| `old/uedcli/tests/test_preview_wire.py` | 8 | perspective wireframe |

Only **five golden fixtures** exist: `preview_wire_golden_{iso,quad}.png`,
`preview_textured_world_golden_iso.png`, `preview_grid_golden.png`, `native_preview_golden.png`.
Each test decodes both sides to raw RGB (`Image.open(...).convert("RGB").tobytes()`) and compares
**byte-for-byte with zero tolerance**, reporting a differing-byte count on failure; `UEDCLI_BLESS_GOLDEN=1`
re-blesses. PNG is storage only, so encoder settings never enter the comparison. Numeric `pytest.approx`
tolerances appear only in formula unit tests (plane fits, shade, grid fade), never on an image.

Portability consequence: the structural majority ports *well* — those tests assert pixel probes, draw
counts, replay invariants and formula values against internal functions, which is what a Rust unit test
does, provided the port keeps equivalent seams (`_fill_face`, `_face_shade`, `_mip_level`,
`_auto_locator_lattice`, `_max_inscribed_box`). The dispatch-level ~100 are natural differential tests
against `old/bin/uedcli`. The five goldens are the hard constraint: a from-scratch Rust renderer will
not reproduce them byte-exactly unless it reproduces every rounding rule.

### Rust 2D rasterization crates

| Crate | Version | Licence | Maintenance | CPU/GPU | AA | Text | PNG | Cross-platform bit-exact |
|---|---|---|---|---|---|---|---|---|
| `tiny-skia` | 0.12.0 (2026-02) | BSD-3 | low but alive (linebender) | CPU | Skia scanline AA | **no** | yes (`png-format`) | no self-claim; `resvg` claims it de facto |
| `vello_cpu` | 0.3.0 (2026-10-02) | Apache-2.0/MIT | very active | CPU | sparse-strip analytic AA | yes | yes | no claim; runtime SIMD dispatch |
| `raqote` | 0.8.5 (2024-09) | BSD-3 | **dormant** (last commit 2025-02) | CPU | scanline | via `font-kit` (system fonts) | yes | unverified |
| `cairo-rs` | 0.22.9 | MIT | active (gtk-rs) | CPU + platform | pixman | FreeType/Pango | yes | unlikely — C deps, system drift |
| `femtovg` | 0.27.0 | MIT/Apache | active | **GPU only** | GPU | yes | no | no |
| `vello` | 0.11.0 | Apache/MIT | very active | **GPU compute** | analytic | yes | no | no ([#1314](https://github.com/linebender/vello/issues/1314)) |
| `resvg`/`usvg` | 0.48.1 | Apache/MIT | active | CPU (via `tiny-skia`) | inherits | `rustybuzz`, no system fonts | yes | **yes, explicit** |
| `image` | 0.25.10 | MIT/Apache | active | CPU | n/a (no path rasterizer) | no | yes (`png` 0.18) | pixel-level yes for raw buffers |
| `imageproc` | 0.27.0 | MIT | active | CPU | opt-in per primitive | `ab_glyph` | via `image` | unverified |

`tiny-skia` makes no determinism claim of its own (0 hits for `determinis*` in the repo); the evidence is
resvg's README: "if you render an SVG file on x86 Windows and then render it on ARM macOS — the produced
image will be identical", backed by ~1600 reference tests. Its `simd` default feature is compile-time
`cfg`-gated (SSE2→AVX2, NEON, wasm SIMD128) and can be dropped with `default-features = false`; an open
issue ([#62](https://github.com/linebender/tiny-skia/issues/62)) records i686 x87 float divergence.
`vello_cpu` is the forward-looking CPU renderer but dispatches SIMD at runtime via `fearless_simd` and
has two pixel pipelines (`u8_pipeline` default, `f32_pipeline`) — neither pinned.

The decisive point for uedcli is not determinism but fit: none of these crates offers an aliased,
pixel-centre, z-buffered, texture-sampling fill. `render.rs` already is that renderer, in 1953 lines,
with no dependencies beyond `crate::model::Vec3`.

### Text rendering without system fonts

| Crate | Licence | Scope | Font source | Status |
|---|---|---|---|---|
| `fontdue` 0.9.4 | MIT/Apache/Zlib | rasterize + simple layout, no shaping | `Font::from_bytes`, `no_std` | active, solo-maintained |
| `ab_glyph` | **Apache-2.0 only** | outline + rasterize, no layout | font bytes | active |
| `rusttype` 0.9.3 (2022) | MIT/Apache | rasterize + kerned layout | font bytes | **unmaintained**; README redirects |
| `swash` 0.2.10 | MIT/Apache | full shaping + hinting + colour | font bytes | active |
| `cosmic-text` 0.19 | MIT/Apache | shaping + layout + bidi | `fontdb`; **`fontconfig` on by default** | active |

Only `cosmic-text` pulls system discovery, and only by default. `fontdue` is the most reproducible by
construction — its scalar path vendors fdlibm-derived math rather than calling platform libm — but its
`simd` and `parallel` features are unproven bit-equal to scalar (both off by default). `ab_glyph` is the
most conservative (zero-dependency scalar rasterizer, no SIMD, no rayon) at the cost of an Apache-only
licence. None of the five documents a cross-platform reproducibility guarantee.

Permissively licensed faces for `include_bytes!`, if a real font is ever wanted: Inconsolata
(OFL 1.1, ~105 KB regular TTF — smallest vector option), IBM Plex Mono (~173 KB), Source Code Pro
(~210 KB), JetBrains Mono (~270 KB), Liberation Mono (~320 KB), all OFL 1.1; DejaVu Sans Mono
(Bitstream Vera/Arev permissive, ~341 KB). Bitmap alternatives need no rasterizer and are trivially
deterministic: `font8x8` (crate MIT, data public domain), Cozette 6×13 (MIT), Spleen (BSD-2),
Terminus (OFL 1.1). uedcli's `_FONT` is already in that last family, so a bundled font buys
character-set coverage and proportional metrics — nothing else.

### Deterministic raster output

Divergence sources, roughly by real-world impact: font discovery and version (the dominant one — resvg
loads fonts "in a deterministic order" and renders references with `--skip-system-fonts`); hinting and
subpixel/LCD AA (platform-specific by construction; unhinted grayscale is the reproducible choice);
SIMD-vs-scalar codegen where the two paths are not proven equal; platform libm for transcendentals
(`sin`/`atan`/`pow` are not IEEE-pinned); NaN payloads (explicitly "not guaranteed to be portable");
and rayon `reduce`/`fold` combination order, which is unspecified and so non-deterministic for float
accumulation. **FMA is not a hazard in Rust**: the compiler does not contract silently, and
`f32::mul_add` documents single rounding. PNG encoder settings change bytes without changing pixels
(`png::Compression` is `#[non_exhaustive]`), so hash decoded pixels, never the file — which is already
uedcli's practice.

How projects pin it: resvg uses reference PNGs with `DIFF_THRESHOLD: u8 = 1` (one unit per channel) plus
bundled fonts; `tiny-skia` aims for exactness against Skia; wgpu compares perceptually with a FLIP error
map and `Mean`/`Percentile` thresholds (0.01–0.1, 95–99th percentile), writing actual/diff/stats PNGs on
failure; Skia Gold and Flutter Gold keep per-OS/arch/backend baselines and triage deviations by hand.
Crates: `image-compare` (MIT; RMS, SSIM/MSSIM, histogram), `dify` and `odiff` (MIT; YIQ perceptual diff
with an anti-aliasing detector), `insta` for structural snapshots — its experimental
`assert_binary_snapshot!` is byte-for-byte with no image tolerance.

uedcli is already at the strict end of that spectrum (zero tolerance on decoded pixels), and it can
afford to be: no AA, no hinting, no system fonts, no transcendentals in the fill loop, and `f32.rs`
already documents the intent ("Rust's `f32` is IEEE-754 single with no implicit FMA contraction"). The
one standing caution is rayon — already a dependency, and `build.rs:298` already notes it uses an
order-independent lexicographic reduce for exactly this reason.

### SVG as a first-class target

The decisive external fact: **no multimodal model takes SVG as an image input.** Claude accepts
`image/jpeg`, `image/png`, `image/gif`, `image/webp`; OpenAI accepts PNG, JPEG, WebP and non-animated
GIF. An SVG reaches an agent only as *text* — which for a labeled wireframe is arguably better than a
picture, since the labels and coordinates are literal — or must be rasterized to PNG to use the vision
path at all. SVG is therefore an *addition*, never a substitute.

Mechanics, if wanted: `svg` 0.18.0 (MIT/Apache, composer + parser) or `svg_fmt` 0.4.5 (MIT/Apache, a
"very simple debugging utility to dump shapes"); `svgwriter` has a non-standard licence field and ~1.8k
downloads — avoid. SVG line-diffs and greps natively, but only if emitted stably: one element per line,
fixed decimal places, stable order, no generated ids — otherwise a one-pixel camera change rewrites
every line. For text without a font dependency, glyphs-as-`<path>` is the only byte-identical option
(and loses greppability unless a `<title>`/`data-` attribute carries the label); a generic `font-family`
resolves per machine; a base64 `@font-face` is self-contained but `resvg`/`usvg` honour it only partially
(resvg has "No native text rendering"). The in-plane painted decal has no clean SVG equivalent — a texel
grid inverse-mapped through a projected parallelogram becomes a per-texel `<rect>` soup.

### Software 3-D on CPU, and whether GPU is worth it

There is no maintained Rust CPU triangle rasterizer to adopt. `euc` 0.5.3 (MIT/Apache) is the only
"shaders in Rust on the CPU" crate and its last release is 2021-03-09. `softbuffer` is not a rasterizer
("a way to present a pixel buffer to a window surface", needs window handles — useless headless).
`rasterize` 0.6.9 (MIT) is 2-D vector paths only. The prior art is the tinyrenderer lineage (~500 LOC:
barycentric triangles, z-buffer, texture mapping). Expect to write it — which uedcli already has, twice.

Math crates are a determinism hazard rather than a help. `glam` 0.33 documents only *layout* and serde
equivalence between its SIMD and scalar paths, never numerical equality; `Vec4::mul_add` compiles to
`_mm_fmadd_ps` under `#[cfg(target_feature = "fma")]` and to scalar `mul_add` otherwise, and
`length()`/`dot()` route through SSE horizontal adds — so results depend on `target-feature`/`target-cpu`,
not just on the `scalar-math` feature. `nalgebra` 0.35 is **Apache-2.0 only**. `render.rs` uses its own
`model::Vec3` with plain `f32`, which is the reproducible choice and costs nothing.

Headless GPU works but fails the determinism bar. `wgpu` runs headless on Linux CI with no Xvfb (its own
CI installs Mesa lavapipe and sets `VK_DRIVER_FILES`), but is explicitly not bit-identical across
drivers: its suite compares with `nv-flip` "within tolerance of the expected output" and files reference
images **per backend, per adapter, per driver**. WGSL reserves implementation latitude in its
floating-point accuracy and reassociation/fusion sections (titles confirmed, bodies **unverified**).

PNG encode: `png` 0.18.1 (MIT/Apache) exposes `set_compression`/`set_deflate_compression`/`set_filter`
(default `Filter::Adaptive`); `image` 0.25.10 wraps it plus 13 other formats. Encoding is deterministic
for fixed pixels and settings, but a DEFLATE change across versions can move bytes without moving
pixels — which is why comparing decoded pixels is right regardless. Whether `png` writes a `tIME`
chunk by default is **unverified**.


## Options

| Option | Pros | Cons |
|---|---|---|
| **A. Own rasterizer; `png` crate for encode only** (what `render.rs` already is) | Keeps the exact pixel rules the five goldens pin; no AA to fight; zero rendering deps; `_FONT` ports as a `const` table; in-plane decals port verbatim | Writes line/circle/fill/blit primitives by hand (~600 LOC equivalent); no vector output |
| **B. `tiny-skia` for 2-D, own 3-D fill** | Mature, cross-arch pixel identity claimed via resvg; path stroking and clipping for free | AA must be disabled and the pixel rule still re-derived; no text at all; BSD-3 attribution; still need the z-buffered textured fill it does not provide |
| **C. `vello_cpu`** | Actively developed, has text, CPU-only | No determinism claim, runtime SIMD dispatch, two pixel pipelines; AA is the whole point of it |
| **D. SVG *alongside* raster for the wireframe modes** | Diffable, greppable, resolution-free; labels become literal text an agent reads without vision | No vision model accepts SVG as an image, so PNG stays mandatory; in-plane painted decals have no clean SVG equivalent; a second output format to test |
| **E. Headless GPU (`wgpu`)** | Fast at high resolution; runs on CI with lavapipe, no Xvfb | Not bit-identical across drivers — wgpu's own suite compares perceptually and keys references per backend/adapter/driver |
| **F. Keep Pillow via the strangler indefinitely** | Zero work now | Contradicts the rewrite's "no interpreter, no PyO3" end state |

## Proposal (owner's call — not decided)

Proposed, for the owner to accept or reject: **option A, with the `png` crate for encode and `image`
only where Pillow does real pixel work** (breakdown stitch, mesh thumbnail buffer, lightmap atlas
padding, texture-catalog resample). The renderer's defining properties — aliased integer primitives,
pixel-centre sampling, a bespoke in-plane glyph-decal layout, zero-tolerance goldens — are exactly the
properties a general-purpose 2-D crate removes. `render.rs` is the existence proof that this is small:
1953 lines, no dependencies, `cargo test`-able with no Python.

Two sub-proposals worth separating:

1. **Port `_FONT` as a `const` table, not a font file.** It costs nothing, keeps locator-gutter metrics
   exact, and removes the only real font dependency (Pillow's Aileron) by drawing breakdown captions
   the way quad captions already are.
2. **Decide the goldens' status before writing the renderer, not after.** Either the port is held to
   byte-exact reproduction of the five fixtures (a hard but well-defined bar, and the strongest
   differential test available), or they are re-blessed and the pin is lost — a product decision about
   acceptable divergence, not an implementation detail.

SVG deserves a deliberate decision rather than a default, and can only ever be an addition: PNG stays
mandatory for the agent-looks-at-the-picture path. Its payoff is the other path — an agent *reading* the
diagram as text, and a human diffing it in git. That too is a product question, not a rendering one.

## Open questions / what to verify next

- Does `consolidate-level-preview-native-onto-the-actor` (`to-plan`) still stand as the shape the Rust
  renderer should take? The rewrite supersedes the Python implementation it was specified against, so
  "add perspective to `preview.py`" now reads as "one projection seam, ortho and perspective
  implementations".
- Are the five goldens an acceptance bar or re-blessable? (Proposal 2.)
- Is `--size` staying uncapped? `diagram` has no cap while `render_frame` caps at 16384 — the two verbs
  disagree today.
- Do the `make-actor-preview-faster` levers still matter once the inner loops are Rust? Its option A
  targets ~2–3× on an interpreter; a port likely exceeds that for free, mooting options C
  (`--quality draft`) and D (NumPy).
- Unverified externally: whether `tiny-skia`'s and `fontdue`'s SIMD paths are bit-identical to their
  scalar paths; `tiny-skia`'s own test tolerance; whether Skia Gold's digest is an exact pixel hash;
  whether `png` writes a `tIME` chunk by default.

## Sources

- https://pillow.readthedocs.io/en/stable/reference/ImageFont.html — `load_default()` loads bundled Aileron Regular when FreeType is present.
- https://dotcolon.net/font/aileron — Aileron released "No Rights Reserved" (public domain).
- https://github.com/linebender/resvg/blob/main/README.md + `crates/resvg/tests/integration/main.rs` — cross-arch pixel identity for the `tiny-skia` pipeline; `DIFF_THRESHOLD: u8 = 1`; deterministic font ordering.
- https://github.com/linebender/tiny-skia — `simd` default feature (SSE2→AVX2/NEON/wasm), "exactly the same results as Skia"; issue 62 = i686 x87 divergence.
- https://github.com/linebender/vello — `vello_cpu` 0.3.0 (`text`/`png` features, runtime SIMD); issue 1314 = non-deterministic GPU stroke artifacts.
- https://github.com/jrmuizel/raqote — last commit 2025-02; dormant. https://github.com/femtovg/femtovg — GPU-only.
- https://github.com/mooman219/fontdue — opt-in `simd`/`parallel`, vendored fdlibm math. https://github.com/alexheretic/ab-glyph — Apache-2.0 only. https://lib.rs/crates/rusttype — unmaintained. https://github.com/pop-os/cosmic-text — `fontconfig` in default features.
- https://doc.rust-lang.org/std/primitive.f32.html — no implicit FMA contraction; NaN payloads not portable. https://docs.rs/rayon/latest/rayon/iter/trait.ParallelIterator.html — `reduce`/`fold` order unspecified. https://docs.rs/png/latest/png/enum.Compression.html — encoder settings change bytes, not pixels.
- https://raw.githubusercontent.com/gfx-rs/wgpu/trunk/tests/src/image.rs — FLIP error map, `Mean`/`Percentile` comparison. https://skia.org/docs/dev/testing/skiagold/ — per-platform baselines, human triage.
- https://platform.claude.com/docs/en/docs/build-with-claude/vision and https://developers.openai.com/api/docs/guides/images-vision — accepted image types; SVG is not one.
- https://docs.rs/svg/latest/svg/, https://docs.rs/svg_fmt/latest/svg_fmt/ — SVG emitters. https://github.com/linebender/resvg — "No native text rendering"; ships `fontdb`/`harfrust`/`skrifa`.
- https://docs.rs/glam/latest/glam/ and https://github.com/bitshifter/glam-rs/blob/main/src/f32/sse2/vec4.rs — `scalar-math` feature; `mul_add` → `_mm_fmadd_ps` under `target_feature = "fma"`. https://crates.io/api/v1/crates/nalgebra — Apache-2.0 only.
- https://crates.io/api/v1/crates/euc (last release 2021-03), https://docs.rs/softbuffer/latest/softbuffer/ (not a rasterizer), https://docs.rs/rasterize/latest/rasterize/ (2-D paths only), https://github.com/ssloy/tinyrenderer (prior art).
- https://github.com/gfx-rs/wgpu/blob/trunk/docs/testing.md, `.github/actions/install-mesa/action.yml` — lavapipe headless CI; `nv-flip` tolerance; per-backend/adapter/driver references. https://www.w3.org/TR/WGSL/#floating-point-evaluation — §15.7.4/15.7.5 titles confirmed, bodies **unverified**.
- https://docs.rs/png/latest/png/struct.Encoder.html — `set_compression`/`set_filter`; `tIME` default **unverified**.
- https://lib.rs/crates/image-compare, https://lib.rs/crates/dify, https://github.com/dmtrKovalenko/odiff, https://insta.rs/docs/snapshot-types/ — comparison tooling.
- Font sizes measured by `content-length` on canonical repo files; licence texts taken from project licence pages, not read file-by-file — **unverified** at that level.
