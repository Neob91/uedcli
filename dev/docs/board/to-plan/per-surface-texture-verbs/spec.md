# Spec — per-surface texture verbs, STEP 5 (dimension-dependent capability)

Parent spec: `board/inbox/the-per-surface-verb-split/spec.md` §2.4.4 (`--fit-perimeter` tile fix),
§2.5 (`scale --to`), §2.6 (`align one-tile`), §4.3 (docs). Steps 1–4 are shipped (`origin/master`
`a0c7dff`); this is the last step of that item, and the only capability that needs a texture's pixel
dimensions.

**Supersedes the parent spec's dimension source.** §2.4.4/§2.5/§2.6 route `USize`/`VSize` through
`texture_catalog` ("requires a resolved project and a synced catalog"). **Owner ruling 2026-09-05**:
`texture_catalog` is a curation store (tags/description via `texture classify`) that needs an
explicit `refresh`/`sync` and goes stale when packages change, and it does not own dimensions at
all. Dimensions come from a **cached, direct package read**, the same seam `brush poly set
--texture`'s author-time validation already uses (`utexture.TextureResolver`). Nothing else in
§2.4.4/§2.5/§2.6 changes — the tile-rounding formula, `one-tile`'s frame math, `scale --to`'s
semantics are as specced there. This document is the implementation plan for that corrected seam.

## 1. The dimension lookup — `TextureResolver.dimensions`

New method on `uedcli/utexture.py`'s `TextureResolver`, alongside `exists`/`resolve`/
`package_for_ref`:

```python
def dimensions(self, ref: str) -> tuple[int, int] | TextureError:
    """Mip-0 (USize, VSize) for `ref`, or a TextureError naming why not. Cached by identity per
    resolver instance, like `resolve`/`exists`. Cheaper than `resolve`: `decode_texture` reads the
    header and the raw mip byte arrays but does no RGB/palette expansion, which `dimensions` never
    needs."""
```

**Correction from review**: `package_for_ref(ref)` alone cannot supply this — it returns a bare
`None` for three different reasons (bad ref shape, no such package, package-has-no-matching-texture)
and cannot tell "package unreadable" from "package absent" either (both collapse to `None` from
`self._package()`; only `_decode_ref` disambiguates, by separately checking `self._pkg_unreadable`).
So `dimensions()` must inline the same two checks `_decode_ref` already does — the ref-shape/part
count check, and the `self._pkg_unreadable` lookup after a `None` package — rather than pretending
`package_for_ref` alone is enough. Case vocabulary, deliberately narrower than `resolve`'s: reuse
`unqualified-ref` and `package-unreadable` verbatim (same meaning, same messages); merge `resolve`'s
separate `unknown-package`/`unknown-texture` into one `not-found` (existing author-time validation
already presents both identically — `_validate_texture_ref`'s message is "no Texture of that name
on the package path" either way, so this is not a new merge, just matching current UX); add
`no-mip-data` when `decode_texture` reports `no_mip_data=True` (a procedural texture with no
authored mip 0 — nothing to fit against). Wrap the same exception set `resolve()` guards against
(`ValueError, struct.error, IndexError, KeyError, MemoryError, OverflowError, UnicodeDecodeError`)
into a `TextureError` — never let a corrupt package raise out of this call. One more edge case a
review caught: a texture with an empty `Mips` array but real `CompMips` data has `no_mip_data=False`
(comp-mips carry bytes) and no `mips[0]` to read — `dimensions()` must select `t.comp_mips[0]`
there, **mirroring `_decode_export`'s own mips-or-comp_mips fallback** (`resolve()`/`exists()`
already succeed on such a texture; `dimensions()` failing it with `no-mip-data` would be a new,
undocumented restriction on an otherwise-valid texture, not a bug fix). Only report `no-mip-data`
when BOTH arrays are empty.

New cache: `self._dims_cache: dict[str, tuple[int,int] | TextureError] = {}`, keyed by
`ref.casefold()`, mirroring `_exists_cache`. Per-resolver-instance only, no on-disk cache — the
class docstring's existing caching contract already says this and `dimensions` follows it.

**Test plan**: `uedcli/tests/test_utexture.py` (or a new `test_utexture_dimensions.py`), built on
`pkgfixture.texture_package(...)` the same way `test_texture_cli.py` does — synthesize a `.utx`
with a known `mips=[(256, 64, data), ...]` chain and assert `dimensions()` returns `(256, 64)`.
Cover: a missing ref, a bare (unqualified) ref, a texture with `no_mip_data=True`, and that two
calls return the identical cached object (`is`, like `resolve`'s own cache-identity test if one
exists — check `test_utexture.py` for the pattern).

## 2. The CLI-layer seam — a `resolve_dims` CALLBACK, not a pre-resolved dict

**Revised after review** (the original draft's dict-of-pre-resolved-dims design had two problems:
it forced `test_polyalign.py`'s guard tests through a CLI/resolver stack `polyalign.align()` never
otherwise touches, and it forced the CLI to validate "one shared texture" and "does it resolve"
*before* `run`'s own structural pre-walk — reversing the existing, tested order where structural
problems are diagnosed first).

`polyalign.py` and `surface.py` still stay pure model-side — no `utexture`/`resources` import, per
the architecture note the parent spec already sets for `--fit-perimeter` ("`polyalign` does not
import `texture_catalog`") and now generalises to `utexture` too. But the injection seam is a
**plain callable**, built once by the CLI and passed down, rather than a value the CLI pre-computes:

```python
resolve_dims: Callable[[str], tuple[int, int]]      # ref -> (USize, VSize); RAISES ValueError
                                                     # naming the ref and why, on any failure
```

The CLI builds it once per invocation, only when the mode actually needs it (`one-tile` always;
`run` only under `--fit-perimeter`; `scale` only under `--to`):

```python
def _make_resolve_dims(args):
    _project, _user_config, files = resources.package_path_or_exit(args)   # exit 2 if no project
    resolver = utexture.TextureResolver(files)                             # built ONCE — keeps the cache
    def resolve_dims(ref: str) -> tuple[int, int]:
        result = resolver.dimensions(ref)
        if isinstance(result, utexture.TextureError):
            raise ValueError(f"texture not found: {ref} — {result.detail}")
        return result
    return resolve_dims
```

`ValueError` (not a `polyalign`-specific type), because `apply_scale`'s `--to` path lives in
`surface.py`, which does not import `polyalign` — and the CLI's existing `except ValueError`
handlers already catch both `PolyAlignError` (a `ValueError` subclass) and a plain `ValueError`
identically, so this needs no new dispatch wiring.

**Batching stays where every other guard already lives — inside the mode function, not the CLI.**
`one-tile` and `scale --to` are per-face (no shared frame, each face may carry its own texture), so
each does its OWN pre-pass: collect every face with no bound texture, call `resolve_dims` once per
DISTINCT ref among the rest (catching `ValueError` per ref so one bad ref doesn't stop the pass),
and raise ONE error naming every offender if the pre-pass found any — before writing anything,
exactly the shape §2.3's projection guard and §2.6's own "batch is all-or-nothing" text already
require. `align run --fit-perimeter` needs exactly ONE texture for the whole run (§2.4.4: "a run
whose faces carry different textures … one density cannot satisfy two") — see §3 for where that
check now lives.

## 3. `align run --fit-perimeter` — the whole-TILE fix

Step 4 shipped the guards (closed run, quarter `--turn`) and left the density snap at whole
**texels** (§2.4.4 measured this leaves ~31 texels of residual on the standard 8-sided R=256
cylinder). This step corrects the snap and, since a texture size is now mandatory, removes the
whole-texel fallback entirely (`--fit-perimeter` always needs a resolvable shared texture from
here on — no back-compat "old way" branch).

**Revised after review: the texture requirement lives INSIDE `_run_align`, after the existing
pre-walk, not in the CLI ahead of it.** `poly.texture` is model data `polyalign` already reads
elsewhere (`find_faces`'s `texture` filter), so checking "every walked face carries the same,
non-`None` texture" needs no resolver and can live in `polyalign.py` alongside the run's other
guards — keeping the established rule "the guard belongs in the step that first makes its failure
reachable" and the single ordered validation sequence `_run_prewalk`/`_run_align` already are. This
also means an author who has BOTH a broken run (branching/open) AND no texture bound sees the
structural diagnosis first, exactly like today — texture is the last thing checked, since it is the
newest requirement.

**`polyalign.py` (`_run_align`)** — signature gains `resolve_dims: Callable[[str], tuple[int,int]]
| None = None`. The `fit_perimeter` branch, after the existing closed-run and quarter-turn guards:

```python
if fit_perimeter:
    if not closed: raise PolyAlignError(...)                    # unchanged, step 4
    if turn_uu % 16384 != 0: raise PolyAlignError(...)           # unchanged, step 4
    refs_by_idx = {idx: actor.brush.polys[idx].texture for idx, _, _ in walk}   # poly.texture, per walked face
    missing = [idx for idx, ref in refs_by_idx.items() if ref is None]
    if missing:
        raise PolyAlignError(f"... {len(missing)} face(s) carry no texture — {...}")
    distinct = {ref.casefold() for ref in refs_by_idx.values()}   # CASEFOLDED — matches every other
    if len(distinct) > 1:                                         # texture-ref identity check in the codebase
        raise PolyAlignError("... faces carry different textures — one density cannot satisfy two — "
                              "split the run or set one texture first: {...}")
    ref = next(iter(refs_by_idx.values()))                        # the one texture, original casing
    w, h = resolve_dims(ref)                                     # may raise ValueError; propagates as-is
    tile_texels = w if (turn_uu // 16384) % 2 == 0 else h        # unchanged stored-axis rule, §2.4.3/§4.2
```

Then the rounding itself:

```python
target = max(tile_texels, round(total_chord / tile_texels) * tile_texels)
d = target / total_chord
```

(`max(tile_texels, …)` is `fit_demo.py`'s own corrected-mode implementation, algebraically the same
guard as the parent spec's `max(1, round(total/T))·T` — both prevent a run shorter than half a tile
from rounding to zero tiles and a zero-length axis.)

**CLI (`_align` in `poly.py`)**: when `mode == "run"` and `args.fit_perimeter`, build `resolve_dims`
via `_make_resolve_dims(args)` (§2) and pass it to `polyalign.align(..., resolve_dims=resolve_dims)`;
otherwise pass `None`. No other CLI-side texture logic for this path — no pre-check, no pre-built
dict. `align()`'s own top-level signature (today `align(level, tokens, mode, *, turn=0,
fit_perimeter=False)`) gains `resolve_dims: Callable[[str], tuple[int,int]] | None = None` and
threads it through to whichever mode function needs it (`_run_align`, and `_one_tile_align` in §4).

**One accepted front-running exception, not a gap to close**: `_make_resolve_dims(args)` itself
calls `resources.package_path_or_exit(args)`, which exits 2 if the CLI isn't run inside a resolvable
project — and that call happens before `polyalign.align()` is even invoked, so a structurally broken
run with no project sees "no project" first, not the structural diagnosis. This is fine: a project's
mere existence is a precondition to building a resolver at all (identical to how `_validate_texture_ref`
already exits before touching a level), not a content-dependent check like "do these faces share a
texture" — which DOES now run after the structural pre-walk, per the ordering goal above.

**Test plan** (`test_polyalign.py`, extending the existing `test_run_fit_perimeter_*` tests) —
**now directly testable without any CLI/resolver**, since `resolve_dims` is a plain injectable
callable (`polyalign.align(..., resolve_dims=lambda ref: (256, 256))` in a test, matching how the
existing suite already builds fixtures rather than driving the CLI): the standard 8-sided R=256
cylinder with `poly.texture` set and a fake `resolve_dims` returning `(256, 256)` — assert the
closing-seam gap is `< 1e-3` texels (was ~31 with the whole-texel snap; §2.4.4's own measured
figures: leave 1567.472, whole-texel-fit 1567.000, whole-tile-fit 1536.0 exactly). Also: the "faces
carry different textures" guard on a 2-textured run; the "no texture bound" guard on a freshly-built
untextured cylinder (both need no `resolve_dims` at all — they fail before it would be called); a
non-square texture (256×64, via a fake `resolve_dims`) at `--turn 16384` picks `VSize` not `USize`
(§2.4.4's own "4× error on exactly the case the quarter-turn note was added to protect"); a
casefold-differing pair of refs (`DeusExDeco.Wood` / `deusexdeco.wood`) across two faces does NOT
trip the "different textures" guard. A separate, small CLI-level test (alongside the file's existing
`test_dispatch_poly_align_*` tests, or a new file mirroring `test_texture_cli.py`'s
`monkeypatch.setattr(resources, "texture_resolver", ...)` pattern) checks `_make_resolve_dims`
itself: a real `pkgfixture`-built `.utx` resolves correctly, and a missing project exits 2 via
`package_path_or_exit`'s own message.

## 4. `align one-tile` — new mode

Fit exactly one texture tile to each face, independently — no shared frame, no orientation guard
(any face works; the projection axis is always the world axis the face faces MOST, so `|N·A| ≥
1/√3` always and the wall/floor guard can never fire here). Per §2.6, in full:

**Axis + basis.** `k = argmax_i |N[i]|` over **all three** axes (ties → lowest index — Python's
`max(range(3), key=lambda i: abs(n[i]))` is first-wins, so this falls out for free, same as `wall`'s
tie-break). Take the `(U_src, V_src)` world-axis pair from the SAME table `wall`/`floor` use
(`k=2→(X̂,Ŷ)`, `k=0→(Ŷ,Ẑ)`, `k=1→(X̂,Ẑ)`) — add a `_AXIS_UV = {2: (Xhat,Yhat), 0: (Yhat,Zhat), 1:
(Xhat,Zhat)}` table beside `_projection_axis` (or generalise `_projection_axis` to take the axis
index directly rather than a mode string, and have `wall`/`floor` call it with their own derived
axis — a small refactor that removes the duplication).

**Orthogonalise by Gram-Schmidt of U against V — owner ruling, not `U = V × N`:**

```
V̂ = unit(−proj(V_src, n))                          # kept EXACTLY as the table gives it
raw_u = −proj(U_src, n)
Û = unit(raw_u − V̂ · (raw_u · V̂))                   # square U to V, keep raw_u's sign/side
```

Verified in the parent spec on the corner normal `(0.577,0.577,0.577)`: un-orthogonalised the pair
is 120° apart and the fit overshoots to `[-85.33, 170.67]`; Gram-Schmidt gives exactly 90° and
`[0, 256]`. On every axis-aligned face (the common case) `Û` is already `⊥ V̂` and this is a no-op.
`U = V × N` is rejected — it re-derives its own sign rather than inheriting the table's, mirroring
the image on half the face directions.

**Extent + anchor.** Project every world vertex onto `(Û, V̂)`: `pu_i = v_i·Û`, `pv_i = v_i·V̂`.
`extent_u = max(pu) − min(pu)`, `extent_v = max(pv) − min(pv)` (a zero extent along either axis —
only possible on a degenerate/collinear projection — exits 2 naming the face). Anchor the frame's
`Origin` so the minimum corner maps to `(0,0)`: with `Û ⊥ V̂ ⊥ n̂` (guaranteed by the
Gram-Schmidt step — "exact only because the frame is orthonormal", §2.6), pick any reference vertex
`P0` and set

```
Origin = P0 − (P0·Û)·Û − (P0·V̂)·V̂ + min(pu)·Û + min(pv)·V̂
```

(`P0` minus its own `Û`/`V̂` components — i.e. its component along `n̂`, plus the extremal corner
along `Û`/`V̂`; algebraically the world point whose `Û`/`V̂` projections are exactly `min(pu)`,
`min(pv)`, whatever its normal component). On a rectangular face square to the axes this IS a
vertex, matching the parent spec's stated check.

**Magnitudes.** `density_u = W / extent_u`, `density_v = H / extent_v` (the texture STRETCHES
non-uniformly to fill — that is the point, a letterboxed sign is the wrong operation).
`TextureU = Û · density_u`, `TextureV = V̂ · density_v`, `Pan = (0,0)`.

**Requires a texture, per face, batched.** `_one_tile_align`'s OWN pre-pass (§2): collect every face
with no bound texture; for the rest, call `resolve_dims` once per DISTINCT ref (casefolded),
catching `ValueError` per ref so the pass sees every bad one, not just the first. If the pre-pass
found anything, raise ONE `PolyAlignError` naming every offending face/ref — nothing written.
Reuses `resolve_align_targets` for the target grammar (bare brush name = all its polys, same as
`wall`/`floor`/`run`).

**CLI**: a fourth `align` subparser, `one-tile`, no mode-specific flags (matching §2.0's table — its
row lists none). `_align` always builds `resolve_dims` via `_make_resolve_dims(args)` for this mode
(unconditionally — `one-tile` always needs it, unlike `run`'s conditional-on-`--fit-perimeter`) and
calls `polyalign.align(level, tokens, "one-tile", resolve_dims=resolve_dims)`.

**Test plan**: the flagship corner-face regression from the spike
(`spikes/2026-07-26-poly-rotate-curved-track/uv_preview.py`'s `onetile-ortho` scene: the triangular
corner `[(256,0,0),(0,256,0),(0,0,256)]`, a 256×256 texture) — assert the two axes come out
perpendicular (`dot(TU,TV) ≈ 0`) and the fit spans exactly `[0,256]` on both. A rectangular
axis-aligned face — assert the four corners map to `(0,0)/(W,0)/(W,H)/(0,H)` (in SOME assignment;
which corner is `(0,0)` follows the anchor rule, so pin the actual corner, not just "some
permutation"). The batch-all-offenders guard on a `poly find` result with several untextured faces.
Non-uniform stretch on a non-square face with a non-square texture.

## 5. `scale (--to U,V | --by FU,FV)` — the absolute form

`--by` is unchanged (ships already, step 1; pure math, no project needed). `--to U,V` sets the
**absolute** density in world-units-per-tile (`--to 128,128` ⇒ the bound texture repeats every 128
uu each way) — reusing `apply_scale`'s existing re-anchor (Gram-solve on the centroid, writes
`Origin`/`TextureU`/`TextureV`, leaves `Pan`) rather than duplicating it.

**Refactor `uedcli/surface.py::apply_scale`** to accept the per-face target magnitude as data
instead of a single global `(fu, fv)`:

```python
def apply_scale(level: Level, targets: list[str], *,
                 by: tuple[float, float] | None = None,
                 to: tuple[float, float] | None = None,
                 resolve_dims: Callable[[str], tuple[int, int]] | None = None) -> list[str]:
```

Exactly one of `by`/`to` is set (the CLI's mutex group guarantees it; the function still asserts it
defensively, matching `align()`'s own belt-and-braces style). Internally, resolve per face:

- **`by`**: `(fu, fv)` is the same constant for every face — today's behaviour, unchanged, and
  `resolve_dims` is never called (no project needed, exactly as documented today).
- **`to`**: a pre-pass over the resolved target set (§2's batching shape): every face with no bound
  `poly.texture` is collected; for the rest, `resolve_dims` is called once per DISTINCT ref
  (casefolded), catching `ValueError` per ref; any failures raise ONE error naming every offender,
  nothing written. Then per face: `W, H = dims[poly.texture.casefold()]`; target absolute magnitudes
  `mag_u = W / U`, `mag_v = H / V` (`U, V` the requested world-units-per-tile, validated `> 0` same
  as today's `--by` factor check); convert to the existing relative-factor math the Gram-solve
  already uses: `fu = |TextureU| / mag_u`, `fv = |TextureV| / mag_v` (so `tu2 = tu · (1/fu) = tu ·
  (mag_u/|tu|)`, a vector along the CURRENT direction with the NEW absolute magnitude — the
  re-anchor math is then byte-identical to `--by`'s, just fed a per-face factor instead of a global
  one).

**Drop `--by`'s `(fu,fv) == (1,1)` no-write short-circuit under `--to`** — it is a global-constant
optimisation that does not generalise to per-face factors and the identity case is measure-zero
under an absolute target; always write under `--to` (correctness is unaffected, this is purely
about the git-diff-quiet optimisation `--by 1,1` gets).

**CLI (`cli/parsers/brush.py`)**: `scale`'s parser gains a required mutually-exclusive group
(`--to` | `--by`), matching `pan`'s/`palign run`'s established shape — replacing today's single
required `--by`. `--to`'s help must state the WORLD-UNITS-PER-TILE convention explicitly (the same
"named for what the level designer sees" framing `--by`'s help already uses) so the direction of
the effect (`--to 128,128` on a 256px texture DOUBLES the apparent scale vs `--to 64,64`) is not
left to be discovered.

**Test plan** (`test_surface.py`, extending the existing `apply_scale` tests, using a fake
`resolve_dims` lambda exactly like `test_polyalign.py`'s new run tests — no CLI/resolver needed):
`--to 128,128` on a 256×256-dims face yields `|TextureU| = 2.0`; `--to` on faces with different
bound textures in one set (each gets its own correct magnitude, independently, via one
`resolve_dims` covering both refs); the "no texture bound" and "ref does not resolve" (a
`resolve_dims` that raises for one ref) batch-all guards, both naming every offender; a `--to 0,V` /
negative value exits 2 exactly like `--by`'s guard.

## 6. Docs to update in the same change

| doc | what changes |
|---|---|
| `docs/reference/brush/poly.md` | `scale` section: document `--to`. `align` section: add `one-tile`; correct the `--fit-perimeter` bullet (drop "still leaves ~a whole-texel residual" — it is now exact) |
| `docs/leveldesign/general/textures-and-surfaces.md` | mention `scale --to` and `align one-tile` in the alignment/scrolling section |
| `uedcli/cli/parsers/brush.py` `--fit-perimeter` `help=` | currently says "This still leaves ~a whole-texel residual… the whole-TILE fix… arrives with the catalog" — false once this ships; rewrite to state the exact whole-tile behaviour |
| `dev/docs/rationale/polyalign.md` | a `one-tile` section: the Gram-Schmidt ruling + rejected `U=V×N`, mirroring the existing `run` sections' style |
| `dev/docs/unrealed/texalign.md` | none — this step touches no editor-measured fact |

## 7. Build order (three reviewable pieces, per `CLAUDE.md` "batch small changes")

1. **§1–2**: `TextureResolver.dimensions` + `_make_resolve_dims`. Small, fully testable offline with
   `pkgfixture`, no CLI-visible behaviour change yet (nothing calls `_make_resolve_dims` until
   step 2/3 below).
2. **§4**: `align one-tile` — the riskiest frame math, reviewed alone. Wires `_make_resolve_dims`
   into `align`'s dispatch for the first time.
3. **§3 + §5**: the `--fit-perimeter` tile fix and `scale --to` together — both are "read a texture's
   size for an existing operation" via the same `resolve_dims` callback and the same per-mode
   batching shape, smaller than one-tile, so reviewing them together is cheap. (Split further on
   review if the diff proves unreviewable.)

Each piece: build → scoped tests → one subagent review → fold findings → commit, before the next.
