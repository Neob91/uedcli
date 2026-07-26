# Native UModel (BSP) serialization is byte-exact — VERDICT: GO

**Status: COMPLETE (2026-06-28). A native serializer reproduces a built `UModel`
(BSP) body byte-for-byte from its parsed structure on 72419/72419 Model exports
across all 82 readable v68 Deus Ex retail install maps** (the serializer is
version-agnostic on the shared 68/69 code path; an earlier draft of this doc
mislabeled the corpus "v69" — the install maps are v68, `unrealed/package-format.md`)
— every `Model` export in every map, including all 82 level (largest) Models,
re-serializes byte-identically to the original
`buf[serial_offset : serial_offset+serial_size]`.

This closes the load-bearing unknown that gated the de-containerization "native
geometry write" path. The `Model` *read* parser was already validated byte-exact
to EOF (`spikes/2026-06-25-umodel-serialize-format.md`, 12/12 level maps); the
*write* (serialize-from-structure) was only asserted "mechanical inverse" — it is
now built and measured. A future offline BSP build (D2) can emit a game-valid
`Model` body with no editor, because re-encoding the parsed arrays reproduces the
engine's own bytes exactly.

The harness lives next to this doc:
[`bspspike/umodel_serialize.py`](bspspike/umodel_serialize.py) (the serializer +
inverse primitive encoders) and
[`bspspike/test_umodel_serialize.py`](bspspike/test_umodel_serialize.py) (the
corpus validation + per-map EXACT/MISMATCH table). It builds ON the read parser
[`bspspike/umodel_parser.py`](bspspike/umodel_parser.py) without modifying it.

---

## Reproduce

```
cd Tools/uedcli/dev/docs/spikes/bspspike
# per-map EXACT/MISMATCH table + final "N/M models byte-exact":
/home/human/src/dx_lum/.venv-uedcli/bin/python test_umodel_serialize.py
# or the standalone corpus runner (sample + all-maps sweep):
/home/human/src/dx_lum/.venv-uedcli/bin/python umodel_serialize.py
# or pytest (3 tests; ~125s — the prefix-ambiguity test re-walks every model twice):
/home/human/src/dx_lum/.venv-uedcli/bin/python -m pytest test_umodel_serialize.py -q
# one map:
/home/human/src/dx_lum/.venv-uedcli/bin/python umodel_serialize.py <path.dx>
```

Result: `72419/72419 models byte-exact` across the 82 v68 install maps (the runner
prints a "v69 maps" label — that is the corpus mislabel noted above; the maps are v68).

---

## What is re-emitted from STRUCTURE vs RAW passthrough

This split is the whole point — it pins exactly what the proof covers. A
structured segment is re-encoded field-by-field through inverse primitives (so a
field change provably alters the output bytes); a raw segment is spliced back
from the original `(start, end)` span.

**Re-emitted from parsed structure (the geometry — what D2 must generate):**

| Segment | Encoder |
|---|---|
| `Vectors` TArray (`FVector`) | `enc_fvector_array` → `ci` count + `f32×3` each |
| `Points` TArray (`FVector`) | same |
| `Nodes` TArray (`FBspNode`) | `enc_node`: `f32×4` plane, `u64` zone_mask, `u8` flags, 11× `ci`, 2× `i32` |
| `Surfs` TArray (`FBspSurf`) | `enc_surf`: `ci`, `u32` poly_flags, 6× `ci`, 2× `u16` zone, `ci` |
| `Verts` TArray (`FBspVert`) | `enc_vert`: `ci` + `ci` |
| `NumSharedSides` / `NumZones` | `i32` each |
| `FZoneProperties[NumZones]` | `ci` ZoneActor ref re-encoded; the 16-byte Connectivity+Visibility QWORD pair spliced raw |
| `field_0x54` | `ci` |
| `Leaves` TArray (`FBspLeaf`) | `enc_leaf`: 3× `ci` + `u64` |

**Raw passthrough (non-geometry; the read parser only skips these):**

- the UPrimitive prefix (FBox + FSphere bounds; see prefix variants below);
- the four aux TArrays before Leaves: `0xa8` (FLightMesh), `0xb4` (lightmap
  BYTEs), `0xc0` (FBox), `0xcc` (INT);
- the `0xe4` (INT) array + the two trailing INTs.

The raw spans are captured by walking the body exactly like
`parse_model_serial` and recording each span's offset; only their *length* must
be known to splice them, never their internal field semantics.

---

## FCompactIndex canonicalization: no issue found

The likely failure mode (a re-encoded `ci` not matching the engine's bytes) **did
not occur anywhere** in 72419 models. The engine writes canonical-minimal `ci`
and `enc_ci` reproduces it exactly. The encoder is the strict inverse of
`umodel_parser._ci`:

- byte 0: bit7 = sign, bit6 = "more bytes", bits0-5 = low 6 bits;
- byte 1+: bit7 = "more bytes", bits0-6 = next 7 bits;
- the continuation bit is set iff a non-zero remainder remains (canonical-minimal).

A 20k-value fuzz + boundary unit test (`_test_primitives`, including signed-zero:
`enc_ci(0) == b"\x00"`, never sets the sign bit) passes, and every `ci` field in
every Node/Surf/Vert/Leaf/Zone round-trips byte-identically across the corpus.

---

## The one real find: a SECOND UPrimitive-prefix length (42 vs 57)

The read parser assumed a fixed **42-byte** UPrimitive prefix
(`ci(None) + FBox(25) + FSphere(16)`). That holds for 72176/72419 models. The
remaining **243** models carry an extra **15-byte lead block** before that
prefix (a 57-byte prefix total) — identifiable because byte 0 is not `0x02` (the
standard `ci(None)` start) but a per-package 2-byte value, followed by
`ff×8 00×4 81`. The lead block is non-geometry (bounds-adjacent) and passes
through raw; only its length matters.

`umodel_serialize.detect_prefix` resolves it by walking the body to EOF with each
candidate length. This is **clean and unambiguous on the whole corpus**: every
model walks to EOF with exactly ONE of {42, 57} — never both, never neither
(asserted by `test_prefix_detection_is_unambiguous`). The read parser's fixed-42
assumption mis-parsed these 243; for 242 the misparse coincidentally produced
self-consistent empty arrays and still reached EOF (so a faithful re-serialize was
byte-exact anyway), but one (`00_TrainingCombat.dx` `Model413`, 9 vectors / 6
nodes of real geometry) mis-read the Vectors floats and would have mismatched at
offset 43 — detecting the correct prefix fixes it and is the reason the serializer
does its own prefix detection rather than reusing the parser's `_PREFIX`.

**This is a parser-prefix gap the serializer now handles; `umodel_parser.py` was
left unmodified** (its `native_render.py` and other callers still import it). A
follow-up could fold `detect_prefix` back into the parser so it, too, reads these
243 models correctly.

---

## What did NOT reach byte-exact, with the precise reason

- **`Entry.dx` — 1 map, NOT a serialize failure.** It is a **version-61** package
  (normal install maps are v68). Its *name table* uses the v61 format (null-terminated
  string + 4-byte flags, no compact-index prefix — the same v61 quirk documented
  for the 5 v61 content packages in `unrealed/quirks.md`), which
  `umodel_parser._read_name` (the v68/v69 `ver>=64` reader) can't read, so
  `find_model_exports` raises before any Model is reached. Locating its Models with a
  v61-aware name reader confirms it DOES contain `Model`/`Model2`/`Model4` exports, but
  their **UModel serial body is also v61-shaped** (different field layout — `detect_prefix`
  rejects it), so this is a v61-vs-v68/69 format difference end to end, not a v68
  serialize bug. Entry.dx is the tiny game-entry screen; the validated corpus is v68
  (the on-disk format is shared with v69). Out of scope, flagged honestly.

Everything else: **0 mismatches, 0 exceptions** across 72419 v68 Model exports.

---

## What the next step (native `.dx` write + game-load) must watch for

1. **The geometry proof is for RE-serialization of an already-built `Model`.** It
   proves the serial *format* inverse is exact — NOT that uedcli can *generate*
   the node/surf/vert/leaf/zone arrays. Generating them is the offline BSP/CSG
   build (D2). This spike removes the "serialization is an unverified second port"
   risk; the long pole remains the build that produces the arrays.
2. **No aux array was found to carry an internal absolute file offset** — the
   `0xa8/0xb4/0xc0/0xcc/0xe4` arrays are self-contained counts+payloads spliced
   verbatim, and the `FBspNode.i_collision_bound`/`i_render_bound` are array
   *indices* (-1 sentinel), not byte offsets. A D2 build that synthesizes these
   from scratch must produce valid indices, but a re-serialize never has to
   relocate an offset. (When D2 writes a NEW body whose array lengths differ, the
   EXPORT-TABLE `serial_offset`/`serial_size` and any package-level offset must be
   recomputed by the package-container writer — that is the container writer's job,
   already proven byte-exact in spike 03 of the de-containerization series — not
   the Model body's.)
3. **`ci` is canonical everywhere** in this corpus, so a D2 writer using `enc_ci`
   matches the engine. (Were a non-canonical `ci` ever to appear in foreign
   content, `enc_ci` would re-canonicalize it and diverge — none observed.)
4. **Two prefix variants exist** (42/57). A native writer that synthesizes a
   `Model` must emit the right one; the standard 42-byte (uncomputed-bounds)
   prefix is the natural choice for a freshly built level Model, matching every
   v69 *level* Model in the corpus.
5. **The decisive remaining game-side gate** (per `decisions.md` 2026-06-28) — does
   a `Model` written *natively by uedcli* (not via the editor's `EDIT PASTE`) load
   and spawn in the actual game? — is now unblocked on the serialization side: the
   body bytes are reproducible exactly, so a hand-built minimal carved-room `Model`
   can be emitted natively and load-tested in `dx-game`.
