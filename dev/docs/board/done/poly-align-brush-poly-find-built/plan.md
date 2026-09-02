# Build plan — item 11: `brush poly align` + `brush poly find`

Ephemeral build scratch. Design authority: `dev/docs/decisions.md` 2026-07-18 21:40 UTC
(`poly align` v1 scope + face-selection grammar) and `spec.md`
(UV math + algorithms). This plan sequences the build; durable knowledge folds into
`architecture.md` + `unrealed/t3d.md` on landing.

## Deliverables

1. **`uedcli/polyalign.py`** — pure model-side texture-vector math + face-set/continuity logic.
   - `resolve_align_targets(level, tokens)` → ordered, deduped `[(brush, poly_idx)]` from either
     bare actor names (= all polys) or `BRUSH:SELECTOR` tokens (what `poly find` emits). Order is
     preserved (ring seam = first).
   - `find_faces(actor, *, item, facing, texture)` → `[poly_idx]` for `poly find`.
   - `align(level, targets, mode, *, fresh_frame, fit_perimeter)` → sorted touched brush names.
     Modes: `wall`/`floor` (coplanar shared-world-frame) and `ring` (chord-advance wrap).
   - World-frame extraction reuses `preview_native._world_uv_frame`; write-back is its inverse
     through each brush's own rotation (`rotation.actor_matrix` + `rotation.inverse`), so
     continuity is defined in WORLD space and stored per-brush.

2. **CLI wiring** (`cli.py`): `brush poly find <brush> [--item][--facing][--texture][--json]`
   and `brush poly align (--wall|--floor|--ring) [--fresh-frame][--fit-perimeter] (targets…|-)`.
   Both get `--target`. Every flag a real `help=`.

3. **Dispatch** (`dispatch.py`): two handlers, mirroring `poly list`/`poly set`. Producer →
   stdout one `BRUSH:idx` per line, summary → stderr, `--json`. Align mutates + `src.save`.
   No exception reaches the user (named errors, exit 2).

## Algorithms

**Coplanar (`--wall`/`--floor`):**
- Validate all faces coplanar (parallel normals + equal plane offset). `--wall` requires the
  plane normal's dominant axis to be X/Y (vertical face); `--floor` requires Z (horizontal). This
  is the concrete, useful distinction between the two flags (an orientation guard catching
  mistakes) — adopt-seed itself is axis-agnostic, so without the guard the two flags would be
  identical (spec §"--wall vs --floor" open sub-point).
- Frame: adopt-seed (default) = first face's world `_world_uv_frame`; `--fresh-frame` =
  `builders._tex_basis(n̂)` (unit → 1 texel/unit), base = seed world centroid, pan (0,0).
- Write that ONE world frame to every face via per-brush inverse. Continuity is automatic
  (shared world frame → a seam vertex maps to the same UV from either face).

**Ring (`--ring`):**
- Single brush only. Axis = normalize(cross of two non-parallel face normals), oriented +Z-ish.
- Validate each face normal ⊥ axis (radial) → caps rejected.
- Per-face U density = `|TextureU|` of seed (adopt) or 1.0 (fresh); shared V axis = seed tv along
  axis (adopt) or axis (fresh).
- Walk faces in input order, `u_cursor` accumulating `chord_i · density` (chord = distance between
  a face's two axis-parallel vertical edges = `2r·sin(π/N)`). Each face's start edge = the one
  shared with the previous face (i>0) / the non-shared one (i=0); frame set so U(start)=u_cursor.
  Shared edges get identical U from both faces → continuity by construction.
- `--fit-perimeter` (ring-only) snaps density so total U texels around the ring is the nearest
  integer (exact meet). Leave-seam is the default. (Offline caveat: true pixel-tile seamlessness
  needs texture dimensions — deferred; noted in docs + inbox.)

Continuity offset lives in float `Origin`; `Pan` stays the seed's integer.

## Tests (offline)
- Coplanar UV continuity golden (shared seam vertex → equal UV from both faces), multi-brush.
- Ring wrap: chord advance, leave-seam vs `--fit-perimeter` (integer total), radial validation.
- adopt-seed vs `--fresh-frame`.
- `poly find` filters (item/facing/texture, json).
- Error paths: unknown brush, bad selector, non-coplanar, wrong orientation, cap in ring,
  `--fit-perimeter` without `--ring`, no mode, empty stdin no-op, multi-brush ring.
- Engine-fact regression: UV formula `U=(V−Origin)·TextureU+PanU` and chord `2r·sin(π/N)`.

## Docs
- `docs/usage.md` — both verbs + worked example.
- `architecture.md` — new module + Commands entries.
- `unrealed/t3d.md` — pin the UV convention.
- Reconcile spec open-decisions → "Decided (decisions.md 2026-07-18 21:40 UTC)".
- Move board item 11 → done; file deferred follow-ups to inbox.
