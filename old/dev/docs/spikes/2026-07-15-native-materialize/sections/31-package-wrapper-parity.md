# Native `.dx` package-WRAPPER byte-parity vs UnrealEd

**Scope.** The package *wrapper* = everything the writer serializes AROUND the object
bodies: the UE1 header, the **name table**, the **import table**, the **export table**
(object map), and the generation record. This is the tree-independent slice of byte-parity
(the Model geometry BODY has its own BSP-tree-order blocker, tracked separately). Goal:
native `level materialize` byte-identical to UnrealEd "short of timestamps and similar".

**Method.** `harness/wrapper_diff.py` parses native `NativeCastle.dx` vs editor
`Test_Castle.dx` (same castle trunk as input — the trunk was ingested from that very editor
map) and diffs every wrapper field, matching entries by identity so ORDER differences are
reported explicitly. Rebuild the native side with `harness/build_native_castle.py`. Confidence:
✅ = byte-verified against the two maps this spike, 2026-07-18.

---

## The headline finding: full wrapper byte-parity is IMPOSSIBLE from the trunk ✅

UnrealEd's wrapper encodes **editor-session-global state that does not exist in the trunk**.
A from-scratch native build cannot reconstruct it without replaying the exact edit session.
Three independent, load-*irrelevant* things carry that state:

1. **Name-table ORDER = the editor process's global FName-pool order.** The editor writes the
   name table by walking its global FName array and emitting each tagged name in
   *registration* order — a hardcoded `EName` prefix (`OUTSIDE, None, Side, Brush, Scale,
   PointRegion, Level, Region, Tag, Vector, Location, …` — engine names registered at startup)
   followed by per-object names **in the order objects were created during the session**. The
   trunk carries no such global counter, so even after reproducing the hardcoded prefix the
   object-name suffix cannot be ordered to match. (Native writes names first-use-during-assembly;
   `None` is index 0.)
2. **Object NUMBERING is a session-global UObject counter.** The editor's brush-shape UPolys are
   `Polys4, Polys6, … Polys195`; its viewport cameras `Camera6…Camera11`; the default brush
   `Brush1` with shape `Model2`. Those integers count *all* objects ever minted in the session,
   not anything in the trunk. Native derives stable content names instead
   (`Model_<brush>Polys`, `Brush0`, `Model_Level`). The brush-SHAPE Model names DO match
   (`Model_<brushactor>` both sides — that part is content-derived).
3. **Editor-only actors are saved from the live editor.** `Test_Castle.dx` contains **6 `Camera`
   viewport actors** (flags `0x02340000`) + a **`LevelSummary`** object + editor camera state —
   all serialized from UnrealEd's viewport/browser session. The trunk has none; native emits none.

Consequence: the header `generations` record — `(export_count, name_count)` — necessarily
differs (native `(356, 407)` vs editor `(364, 443)`), **as a symptom of the above, not a codec
bug**. This is the same category as the excluded GUID/timestamps: session state, not wrapper
serialization. The 2026-07-15 §30.6 note that "name/import/export order is arbitrary" is correct
*for loading* and is precisely *why* the editor's order is unreproducible content-independent.

---

## What DID diverge as a real writer bug — and is now FIXED ✅

Per-class **export flags** are fully content-independent (they depend only on the object's
KIND, which both sides agree on) and so are a clean parity target. Two were wrong; fixed in
`native/assemble.py`:

| Export kind | Editor | Native (before) | Native (after) |
|---|---|---|---|
| **Brush actor** (default builder + every CSG brush) | `0x02340001` | `0x02070001` | **`0x02340001`** ✅ |
| **CSG brush-shape `Polys`** | `0x00070000` | `0x00340001` | **`0x00070000`** ✅ |

- `0x02340001` = `RF_HasStack | RF_Transactional | LoadForEdit | NotForClient | NotForServer`:
  a brush actor is **edit-only** — the game loads the built world BSP, never the source brushes
  (the engine skips them at runtime). Native previously wrote them load-for-all (0x02070001),
  shipping the source brushes to the game. New value matches every retail `.dx` Brush export.
- `0x00070000` = `LoadForClient | LoadForServer | LoadForEdit` (no Transactional/HasStack): the
  editor writes CSG brush-shape UPolys load-for-all, distinct from their parent shape Model
  (edit-only `0x00340001`). The DEFAULT brush's Polys keep `0x00070001` (with Transactional) —
  native already matched that.

After the fix, **every export class present in both files agrees on flags**
(`wrapper_diff.py` → "EXPORT FLAGS BY CLASS"): Light/LevelInfo/Zone/SkyZone/PlayerStart
`0x02070001`, Brush `0x02340001`, brush Model `0x00340001`, level-BSP Model `0x00070001`,
Polys `{0x00070000, 0x00070001}`, Level `0x00070001`. Only the editor-only `Camera`
(`0x02340000`) / `LevelSummary` (`0x00070004`) classes have no native counterpart.

`pkg_write.py` itself needed **no change** — its header layout, FCompactIndex codec, name/
import/export encoders, and single-generation mint are all byte-correct; every wrapper
divergence was in *what tables* `assemble.py` builds, never in *how* `pkg_write` serializes them.

---

## Residual (accepted — session-encoded, not a codec bug)

| Field | Native | Editor | Class |
|---|---|---|---|
| Header FileVersion | 68 | 69 | caller-set in `build_native_castle.py`; on-disk shape identical — pass `version=69` to match (load-bearing, left to caller) |
| Name-table ORDER | first-use-during-assembly | global FName-pool order | fundamentally unreproducible (§ headline 1) |
| Object numbering | `Model_<b>Polys`, `Brush0`, `Model_Level` | `Polys<N>`, `Brush1`, `Model2` | fundamentally unreproducible (§ headline 2) |
| Editor-only actors | none | 6 `Camera` + `LevelSummary` | fundamentally unreproducible (§ headline 3) |
| LevelInfo singleton name | `LevelInfo_<id>` (trunk) | `LevelInfo0` | trunk-carried vs editor auto-name |
| Export ORDER | LevelInfo, default brush, CSG(polys+model+actor)*, point actors, level Model, MyLevel | actors in placement order, then Model/Polys pairs, LevelSummary, MyLevel last | derivable from trunk `order`, but cannot byte-match while set/numbering differ — deferred |
| Import ORDER + texture-group casing | resolver-call order; `CoreTexSky.Sky` | first-reference order; `CoreTexSky.sky` | order deferred; casing is a `pkgref` group-index lookup detail |

**Verdict.** The wrapper is now byte-parity **on every field that is content-derivable**
(package flags, licensee, per-class export flags, generation-record *shape*, all three tables'
encodings). It is *not* byte-identical overall, and cannot be, because UnrealEd's name-table
order, object numbering, and editor-only actors are session-global state absent from the trunk
— the same reason the GUID and save-timestamps are excluded from the parity goal. Run
`harness/wrapper_diff.py` for the live field-by-field diff + residual classification.
