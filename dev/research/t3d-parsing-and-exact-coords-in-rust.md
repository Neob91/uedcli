# T3D parsing, emission and exact-coordinate fidelity in Rust

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** How should the Rust rewrite parse, model and re-emit T3D with byte-level fidelity to what `old/` produces?

## Summary

- The fidelity target is `old/`'s output, **not** UnrealEd's. `old/` does not round-trip an editor
  export byte-for-byte and is not meant to: it writes every property the editor default-diffs away,
  sorts props by key, drops `Link`, omits a zero `Pan`. The only invariant worth porting is
  `rust_emit(rust_parse(x)) == py_emit(py_parse(x))` for every `x`, plus idempotence.
- The parse layer is a **lossy, regex-driven, line-oriented scan with no error reporting at all** —
  12 regexes, no block-balance check, no syntax errors. Malformed T3D yields fewer actors, silently.
  A faithful Rust port must choose to reproduce that leniency; the house rule "errors name the
  offending value" is not met by this layer today and cannot be met without a behavior change.
- Exact base-10 arithmetic is load-bearing in exactly **one** place: the `CLEAN_EPS` comparison
  `|d − nearest| <= 0.001`. Measured here: over the exhaustive boundary band (integer parts 0..4095,
  offsets `.001000`/`.999000`, both signs) an `f64` port snaps differently on **9,042 of 16,384**
  cases (~55%). Everywhere else `f64` matches.
- A **scaled-`i64` fixed-point** representation (micro-units, 10⁶) reproduces `fmt_vertex` and
  `fmt_loc` byte-for-byte on 365,536 generated cases — including that whole boundary band and
  inputs with 12 decimal places. Zero differences. No decimal crate needed for the wire format.
- Four separate, mutually inconsistent rounding/formatting rules exist and must be ported as-is:
  `clean`/`quantize6` round **half-away-from-zero**; `transform._fmt6` (scale/sheer) rounds
  **half-even** and can emit `-0.000000`; `fmt_coord` prints the exact decimal with trailing zeros
  dropped; the compare path quantizes to **float32**.
- Three different unquote rules coexist (`model`'s `.strip('"')`, `typedprops._unquote`,
  `propedit._dequote`). They disagree on values containing interior quotes.
- `winnow` 1.0.4 is the only stable-1.0, actively maintained parser-combinator in the Rust field;
  `nom` has been idle ~13 months, `chumsky` has no 1.0. But for a line-oriented format winnow's own
  docs concede the case to hand-writing, and the existing parser is 12 regexes — **hand-rolled
  line scanning is the closest match to what has to be reproduced**.
- No Rust T3D parser exists; nothing in the Rust UE ecosystem (`unreal_asset`, `uasset`) touches
  text formats or UE1. Prior art is Python/C# Blender importers; none of them handle precision.
- UE1 stores every coordinate as float32 and `UFloatProperty::ExportTextItem` prints `%f`, so the
  text already carries noise digits past ~7 significant figures. High-precision arithmetic buys
  nothing numerically — only byte-exact passthrough and determinism.

## What we have today

The T3D text surface in `old/`, narrowly scoped to parse + emit + canonicalize:

| File | LOC | Role |
|---|---|---|
| `old/uedcli/model.py` | 307 | parse `MAP EXPORT` T3D → `Level`/`Actor`/`Brush`/`Polygon` |
| `old/uedcli/emit.py` | 303 | the single write path; `clean`, `fmt_vertex`, `fmt_loc`, `emit_*` |
| `old/uedcli/normalize.py` | 526 | computed-prop strip, `canonical_actor_t3d`, identity hash, `compare_view` |
| `old/uedcli/typedprops.py` | 511 | typed value semantics; struct-literal splitter |

≈1,650 LOC core. Adjacent text codecs that must come with it: `old/uedcli/transform.py` (309,
`parse_fscale`/`emit_fscale`), `old/uedcli/rotation.py` (687, `parse_fvector`/`parse_frotator` and
their emitters), `old/uedcli/t3dtree.py` (344, trunk tree I/O + `Name=` strip/inject),
`old/uedcli/propedit/` (1,190, a second struct-text parser). Call the real porting surface ~2,650 LOC.

Test pressure on it: **55 test files, 23,202 LOC** reference `parse_t3d`/`emit_actor`/`emit_brush`/
`fmt_vertex`/`fmt_loc`/`canonical_actor_t3d`. The dedicated ones are `test_emit.py` (303, 29 tests),
`test_model.py` (127, 11), `test_normalize.py` (1,265), `test_typedprops.py` (155),
`test_engine_facts.py` (1,384 — the engine-fact pins). Seven `.t3d` fixtures, 2,886 lines, of which
two (`level_small.t3d`, `brush_subtract.t3d`) are genuine `MAP EXPORT` goldens.

Nothing in `old/uedcli-native/` (32k LOC Rust) parses or emits T3D text — it takes pre-decoded
coordinate arrays and works in `f32` throughout. The text layer is net-new in Rust. The new root
has **zero dependencies** today, so a parser crate would be the first one.

## Findings

### 1. The format quirks that actually bite

Block nesting is `Map → Actor → Brush → PolyList → Polygon`, but the parser does not enforce it:
`parse_t3d_actors` scans for `Begin Actor` at any depth and never looks at `Begin Map`. There is no
balance check anywhere.

Ordering and spelling rules that are load-bearing, all in `emit_actor`/`emit_polygon`:

| Rule | Why | Consequence of getting it wrong |
|---|---|---|
| `Brush=Model'…'` emitted **after** the `Begin Brush…End Brush` block | matches the editor's own `EDIT COPY` order | brush renders but `ACTOR SELECT INSIDE` silently skips it |
| `Group=` **always** quoted (`quote_group`) | unquoted multi-group values drop groups on import/paste | silent data loss |
| zero `Pan` never emitted; zero `Flags` never emitted | a poly sub-field is an `FPoly` field with no class default, so absent ≡ zero; the editor writes only the non-zero form | a redundant line shifts the whole-block geometry text compare and aborts `level materialize` with a bogus *vertex* mismatch |
| poly `Link` never emitted | computed BSP cross-reference | spurious diff on every re-export |
| an actor property is **never** omitted to mean zero | an omitted property re-imports as the *class* default, which is non-zero for some classes | three live silent-corruption bugs (`Engine.Camera` default `Location`, `TNM.LavaSpitter` default `Rotation`, `TNM.Trestkon` default `Tag`) |
| props sorted by key in `canonical_actor_t3d`; geometry in declared order | determinism vs winding is authored data | reordered winding inverts a solid; CSG GPF |
| no trailing newline after `End Actor` | verified on a real trunk file: last bytes are `End Actor` with no `\n` | every trunk file differs |
| fixed indentation: 0 / 4 / 7 / 9 spaces; `{kind:<8}` + one space for vec lines | — | byte diff on every line |

Property-line forms the parser accepts (five value shapes, two key shapes):

- scalar `Key=Value`, where Value is a number, a quoted string, a bare identifier, a struct
  `(A=1,B=(X=2))`, or an object ref `Class'Pkg.Name'`;
- indexed static array `Key(N)=Value` — `_PROP` captures `(N)` as part of the key, and `prop_key`
  splits it back to `(casefolded name, index)`.

Nested struct values carry quotes inside them (`Region=(Zone=LevelInfo'MyLevel.LevelInfo0',iLeaf=-1)`),
so any member split must be depth- **and** quote-aware — which `split_struct_members` is, and which
`transform._SCALE_INNER_RE` (`Scale=\(([^)]*)\)`) is **not**.

Winding, not `Normal`, defines a face: the importer recomputes the normal, so an authored
`(0.707,0.707,0)` re-exports as the true slope. `canonical_actor_t3d` keeps `Normal` (authored data,
durable trunk) while `_geometry_text` drops it (compare only). Do not conflate the two.

Comments: only bare `//` is stripped by the importer (`ParseLine`, `Exact==0`) — `/* */` and `;` are
not comments. uedcli rides `// uedcli-folder:` and `// uedcli-labels:` carriers on that, read back by
`_FOLDER_CARRIER` and `_LABELS_CARRIER`. A `//` inside a quoted value is **preserved** by the editor,
and uedcli's parser never strips `//` from a property value at all — an asymmetry, currently harmless.

What T3D cannot carry: `myLevel` embedded resources, computed BSP, lightmaps, pathnode reachspecs.

### 2. What the parse layer loses — and must keep losing

| Loss | Mechanism | Does it matter? |
|---|---|---|
| all quoting on property values | `_PROP` → `val.strip('"')` strips *every* leading/trailing quote char | yes — `typedprops` has to recover absent-vs-`""` from the schema instead |
| `Origin`/`Normal`/`TextureU`/`TextureV` precision | `_vec` returns `float`, only `Vertex` uses `_vec_decimal` — four of five fields violate the declared `Vec3 = tuple[Decimal,…]` | byte-invisible (see §3), but the type contract is a lie and a Rust port must decide deliberately |
| duplicate actor names | `parse_t3d` dict-keys by `Name`, last wins; `parse_t3d_actors` preserves them | yes — any raw-user-T3D ingest must use the list form or silently drop actors |
| fractional `Pan` | `int(pm.get("U", 0))` would raise `ValueError` → traceback | latent; `PanU`/`PanV` are ints in `FPoly`, so unreachable on real data |
| which `Location` axes the source stated | recorded out-of-band in `Actor.location_text`, self-invalidating (trusted only while it re-parses to the current triple) | yes — the `Engine.Camera` bug |

`parse_fvector` accepts `-?\d+\.?\d*` while `model._LOC_AXIS` accepts `[-+]?\d+\.?\d*`. Since
`_stated_axes` validates `location_text` through `parse_fvector`, a `+`-signed `Location` axis would
fall back to "all axes stated". The editor does not sign `Location` (only `Vertex`-family lines), so
this is latent, not live.

`parse_frotator` reduces components `% 65536`; the compare path deliberately bypasses it, because
reducing would rewrite 20,109 of the corpus's 23,960 `Rotation` components to zero and make an
over-range rotator compare equal to an unrotated actor. Two parsers for one syntax, with opposite
semantics, both needed.

### 3. The coordinate-precision contract, stated as porting rules

Measured and verified in this session (Python 3, `decimal` + IEEE-754 `f64`):

1. **`CLEAN_EPS = 0.001`, snap on `<=`.** `clean(v)`: let `n = round_half_away_from_zero(v)`; if
   `|v − n| <= 0.001` return `n`, else return `quantize(v, 1e-6, half-away-from-zero)`.
2. **`fmt_vertex`** = `clean`, then sign, then integer part zero-padded to 5, then `.`, then 6
   fraction digits. Total width 13 for `|x| < 100000` — confirmed against `brush_subtract.t3d`
   (every field is exactly 13 chars). Equivalent to printf `%+013.6f` on the cleaned value.
3. **`fmt_loc`** = `clean`, then `.6f`, with an explicit `if d == 0: d = 0` guard so a tiny negative
   never prints `-0.000000`.
4. **`quantize6` is where the magnitude wall lives.** Verified: `Decimal(10)**21` quantizes to 6 dp;
   `10**22` raises `InvalidOperation` (28-digit context precision), converted to a `CoordinateError`
   naming the value. `fmt_loc` has **no** wall for integral values — `1e30` emits fine, because
   `clean` returns via the integer-snap branch and never calls `quantize6`. Two emitters, two ranges,
   deliberately.
5. **`transform._fmt6` (scale/sheer) rounds half-EVEN, not half-up.** Verified:
   `f"{Decimal('1.0000005'):.6f}"` → `1.000000` (context default `ROUND_HALF_EVEN`) while
   `quantize(…, ROUND_HALF_UP)` → `1.000001`. And `_fmt6`'s zero guard tests `d == 0`, which
   `Decimal('-0.0000005')` fails — so `emit_fscale` **can** emit `-0.000000`. Latent quirk; a
   candidate for the `TODO`-in-new-code treatment the rewrite spec prescribes.
6. **`emit_fscale` omits a `Scale` axis equal to 1.0** and the whole `Scale=(…)` when all three are;
   `SheerRate` when 0; `SheerAxis` always. `emit_fvector`/`emit_frotator` omit zero components. Three
   different omission rules for three struct types.
7. **The compare path is float32, not decimal.** `normalize._to_f32` and `typedprops._f32` do
   `struct.unpack("f", struct.pack("f", x))`. `_to_f32` then does `Decimal(repr(f))` — i.e. the
   float's *shortest* repr. A Rust port must use `f32 as f64` and shortest-round-trip formatting here,
   not the 6-dp path.
8. **`parse_decimal` admits an unbounded exponent.** It rejects the `nan`/`inf` spellings but
   `1e999999999` is a finite `Decimal` and passes (known, filed on `board/inbox/`). `propedit._dec_finite`
   separately bounds at `3.4e38`. Any Rust fixed-width type changes which inputs are accepted.

**The measurement that decides the representation.** The only operation that needs exact base-10 is
rule 1's comparison. An `f64` port diverges there, and only there:

| Input domain | cases | `f64` + `{:.6}` differs from `Decimal` |
|---|---|---|
| 6-dp, `\|x\| <= 65535` (the UE1 world) | 400,000 random | 1 |
| 6-dp, `\|x\| <= 1e9` | 100,000 random | 0 |
| 6-dp, `\|x\| <= 1e12` | 100,000 random | 95,872 |
| 12-dp, `\|x\| <= 65535` | 100,000 random | 1 |
| **exactly on the boundary** (`N.001000` / `N.999000`, `N` in 0..4095, both signs) | 16,384 exhaustive | **9,042** |

The single in-range failure is `14014.001000`: in `f64`, `14014.001 − 14014.0 = 0.0010000000002037268`,
which is `> 1e-3`, so `f64` keeps the fraction where `Decimal` snaps to the integer. The frequency in
random 6-dp data is ~2e-6 — but any coordinate a user *types* one millimetre off the grid
(`--at 0,0,0.001`) lands on it deterministically.

`old/`'s own analysis (`board/inbox/flag-to-build-md-and-inbox-md-both-own-the-xfer/spec.md`)
verified the *other* direction — 2,000,000 random 6-dp coords through `float` vs `Decimal`, zero
differences — and concluded `f64` is byte-safe. That conclusion is correct for its scope (storing a
*parsed* 6-dp value as `float` and re-cleaning it) and does not cover the boundary band, where the
comparison itself is the thing that differs.

**Scaled-`i64` reproduces `Decimal` exactly.** Micro-units (value × 10⁶, `i64`), with half-away-from-zero
at the parse step and integer arithmetic for the snap: **0 differences from `Decimal` across 365,536
cases** — 200,000 random 6-dp, 100,000 random 12-dp, and the boundary band exhaustively over eight
offsets × 4,096 integer parts × both signs. Range is ±9.22e12 micro-units, ~2.8e8 times the UE1
world's ±32768.

### 4. Rust parser options

All versions and dates from the external sweep; see Sources.

| Option | Version / activity | Errors naming the offending value | Streaming | Debug build / parse (rosetta JSON) | Fit |
|---|---|---|---|---|---|
| `winnow` | 1.0.4 (2026-07-13), 1.0 stable, repo pushed 2026-10-01 | `ContextError` + `StrContext`; `ParseError::char_span()` gives the byte range — you format the value yourself | `Partial<&str>` + `ErrMode::Incomplete` (re-parses from scratch) | 1s / 27ms | strong; used by `cargo`, `toml_edit`, `gitoxide` |
| `nom` | 8.0.0 (2025-01-26), last commit 2025-08-26 (~13 months idle) | `VerboseError`/`convert_error` **moved out** to `nom-language` in 8.0; docs say write your own | yes | 3s / 68ms | avoid for new work; winnow is its fork |
| `chumsky` | no 1.0; latest stable 0.13.0 (2026-05-06) after the alpha line was renumbered down; moved to Codeberg, active | best in class: `Rich` (found token + span + expected set), `ariadne` rendering, real multi-error **recovery** | — | 5s / 47ms | only option if you want every bad line reported in one pass; versioning risk |
| `pest` | 2.9.2 (2026-09-21), healthy | good "expected X, found Y", but phrased in *rule* names, not domain values | — | 3s / 62ms | weakest fit: grammar in a separate `.pest` file, decoupled from the structs you must round-trip; 3.2× slower than nom on a line-oriented log format |
| `logos` + hand-rolled | 0.16.1 (2026-01-30) | `Lexer::span()`/`slice()` give span + offending text free | n/a | 6s / 22ms | you hand-write all nesting and re-emission |
| `lalrpop` | 0.23.1 | — | — | 12s / 40ms, +1.5 MB binary | LR(1) buys nothing for an unambiguous line format |
| plain hand-written | — | whatever you write | n/a | best | winnow's own docs recommend it for "small, stable formats"; rustc's lexer is hand-written |

Nobody has published LOC or effort data for a T3D-shaped grammar in any of these — unverified.

### 5. Rust exact-arithmetic options

| Option | Arbitrary precision | Preserves parsed scale (trailing zeros) | quantize + rounding modes | Notes |
|---|---|---|---|---|
| scaled `i64` (10⁶) | no (±9.22e12) | n/a — scale is fixed at 6 | hand-rolled | **0 diffs vs `Decimal` on 365,536 cases, measured here**; no dependency; you hand-write parse/format/round |
| `rust_decimal` 1.43 | **no** — 96-bit mantissa, 28–29 digits, `MAX_SCALE = 28` | yes | yes, but `rescale` rounds half-away-from-zero while `round_dp` defaults half-even | widest ecosystem; `from_str` silently rounds past 28 digits, `from_str_exact` has a parser bug (#839). With scale 6 the ceiling is ~7.9e22 vs Python's 1e22 wall — **different error boundary** |
| `bigdecimal` 0.4.11 | yes (`BigInt` mantissa + `i64` scale) | yes | yes (`with_scale_round`, half-even default) | only true arbitrary-precision option; slowest (heap per value); **`Display` adds trailing zeros and uses scientific notation for small fractions — use `to_plain_string()`** (thresholds not crisply specified; verify empirically); repo says it is "currently being re-written" |
| `fastnum` 0.7.5 | compile-time-fixed width (64–512 bit; `Decimal<2>` ≈ 38 digits) | yes | real `quantize(self, other)`, 7 modes (default `HalfUp`) | closest behavioural twin of Python `Decimal`; slowest of the fixed-size crates; `no_std`, mostly `const` |
| `dashu` / `DBig` 0.6.2 | yes, with a `Context` precision model | **unknown — likely no** (it is a significant-digit base-10 float, not scale-carrying) | yes, pluggable | closest to Python's *context* model; unsuitable for byte-exact text round-trip without testing (unverified) |
| `fraction` | yes | **no** — a rational has no scale | n/a | `-1024.000000` and `-1024` are one value with no memory of which was written. Not a fit |
| `f64` + `{:.6}` | no | n/a | exact-mode formatter below ~1e9 | reproduces every well-formed coordinate *except* on the `CLEAN_EPS` boundary (§3) |

Does UE1's own precision make this moot? Partly. `FVector` is `FLOAT X,Y,Z` (32-bit) serialized as
raw binary, and `UFloatProperty::ExportTextItem` is `appSprintf(ValueStr, "%f", …)` — C `%f`, six
decimals. Six decimals printed from a float32 exceeds float32's ~7 significant digits, so the text
already carries noise. Exactness buys **text preservation and determinism**, never numerical
accuracy. If the goal were matching UnrealEd, `f32` arithmetic + `%f` would be the faithful model;
the goal here is matching `old/`, which chose exact decimal.

### 6. Prior art

- **No Rust T3D parser exists.** crates.io searches for t3d/unreal return only binary UE4/5 asset
  readers. `unreal_asset` 0.1.16 and `uasset` 0.6.0 are binary `.uasset`/`.umap` readers, UE4+ only,
  no text formats, no UE1. Nothing to reuse.
- **UELib / UE Explorer** (EliotVU) is C#, decompiles *binary* UE1–3 packages, and *emits* a
  pseudo-T3D property view — not a T3D parser. Worth reading only as a reference implementation of
  UE1 property typing and defaults, which `old/uedcli/uprops.py` already covers.
- Other-language T3D tooling: `crapola/blender_t3d` (Python, import + export, targets old UnrealEd;
  known axis swap and unit-scale caveats, no precision handling), `DarklightGames/bdk_addon`
  (UE2 level authoring from Blender, T3D clipboard both directions — the most serious of them),
  `reszy/UEdConverter` (UE1.5 t3d↔obj, round-trip by design), `mildred/t3d2map`,
  `lcultx/t3d-parser` (TypeScript, last pushed 2016). None address coordinate fidelity.
- Pitfalls others hit match ours: the importer ignores `Normal` and recalculates, and bad
  recalculation on complex brushes permanently breaks lighting; BSP is absent from T3D so the map
  must be rebuilt; copy/paste in UnrealEd *is* T3D serialization.

## Options

**Parsing.**

| Option | Pros | Cons |
|---|---|---|
| Hand-rolled line scanner (direct port of the 12 regexes, no crate) | matches what must be reproduced, including the leniency; zero dependencies in a zero-dependency root; fastest build and runtime; spans and offending text are whatever you write | no combinator safety net; the leniency has to be deliberate, not accidental |
| `logos` lexer + hand-rolled recursive descent | spans and offending slices free from `Lexer`; the one place a tokeniser earns its keep is struct literals, where quote/depth awareness is already hand-written in `split_struct_members` | a DFA lexer over a format whose "tokens" are whole lines is a poor shape match |
| `winnow` | stable 1.0, real maintenance, good track record; `char_span()` makes the house error rule mechanical | a combinator parser naturally *rejects* malformed input, which is the opposite of today's behavior — every leniency becomes an explicit `opt`/`alt` arm |
| `chumsky` | only option that reports every bad line in one pass | no 1.0; and multi-error recovery is a feature `old/` does not have, so it is new behavior |
| `pest` | grammar as documentation | grammar decoupled from the round-trip structs; slowest; rule-named errors |

**Coordinate representation.**

| Option | Pros | Cons |
|---|---|---|
| scaled `i64` micro-units | measured 0 diffs vs `Decimal` on 365,536 cases incl. the whole boundary band; no dependency; trivially `Copy`, `Ord`, hashable; exact `CLEAN_EPS` comparison is one integer subtract | ±9.22e12 ceiling, so the 1e22 `CoordinateError` and `parse_decimal`'s unbounded exponent need a new, explicitly-designed range error; `fmt_coord`'s "exact decimal, trailing zeros dropped" can't echo a >6-dp authored value |
| `f64` | simplest; matches the engine's own model; the computed-geometry modules already work in float | diverges on the `CLEAN_EPS` boundary (9,042/16,384 measured); no way to preserve a parsed scale |
| `rust_decimal` | drop-in-ish `Decimal` feel, serde, wide use | 28-digit ceiling ⇒ a *different* magnitude-error boundary than Python's; `rescale` rounding mode mismatch to re-check per call site |
| `bigdecimal` | the only true Python-`Decimal` equivalent on precision | slowest, heap per value, `Display` is a byte-fidelity trap, crate self-described as mid-rewrite |
| `fastnum` | closest semantics (real `quantize`, 7 modes, scale preserved) | fixed compile-time width; slowest fixed-size crate; smallest ecosystem |

## Proposal (owner's call — not decided)

Three proposals, independently acceptable or rejectable:

1. **Represent coordinates as a newtype over scaled `i64` micro-units**, not a decimal crate and not
   `f64`. It is the only option measured byte-identical to `Decimal` on the `CLEAN_EPS` boundary, it
   adds no dependency to a zero-dependency root, and it makes `clean` a two-line integer function.
   The tradeoff to accept consciously: the magnitude-error surface changes, so the two
   `CoordinateError` messages and `parse_decimal`'s unbounded-exponent behavior need a deliberate
   Rust design (a range check naming the value) rather than a port.
2. **Hand-write the parser** as a direct port of the line scan, with no parser crate for PR #2.
   Revisit if the struct-literal and property-value grammar turns out to want combinators; the
   natural upgrade path is `winnow`, which is the only stable, maintained option. Reason: the thing
   being reproduced is a lenient line scanner with no error reporting, and a combinator parser's
   default behavior is the opposite.
3. **Pin the contract before porting it.** Extract the two real `MAP EXPORT` goldens plus every
   trunk `actor.t3d` in the repo as byte fixtures, and add a differential test in the shape of the
   existing `tests/proxy.rs` that drives `old/bin/uedcli` and the new binary over the same T3D and
   diffs bytes. A property test over the `CLEAN_EPS` boundary band belongs in the same PR — it is the
   one place a plausible representation choice silently diverges.

Flagged for the `TODO`-in-new-code treatment the rewrite spec prescribes (real bugs in `old/`, not
to be fixed there): `emit_fscale` can emit `-0.000000`; `_fmt6` rounds half-even where `clean` rounds
half-up; `_vec` stores `float` into declared-`Decimal` fields; `parse_fvector` and `model._LOC_AXIS`
disagree about a leading `+`; fractional `Pan` would traceback; three mutually inconsistent unquote
rules.

## Open questions / what to verify next

- **Is the `CLEAN_EPS` boundary reachable from a real workflow?** The measurement proves `f64` and
  `Decimal` disagree there; it does not prove any authored level hits it. Worth grepping the trunk
  corpus for coordinates exactly `.001`/`.999` off an integer before weighting it.
- **Scale/sheer rounding.** The scaled-`i64` validation covered `fmt_vertex`/`fmt_loc`. `_fmt6`'s
  half-even path was not validated against a fixed-point port — do that before committing.
- **Rust's `{:.6}` exactness.** No Rust toolchain in this environment, so the claim that
  `f64` + `{:.6}` is exact-mode below ~1e9 is from the `core::fmt::float` source listing only, not
  measured. A property test is cheap and should precede any reliance on it.
- **`fmt_coord` / `num_coord` divergence.** These echo authored values with trailing zeros dropped
  and no `clean`. How often is either called on a value with more than 6 decimals? If never, the
  fixed-point ceiling is free.
- **Differential-test corpus.** Only 109 `.t3d` files and 72 `actor.t3d` trunk files are in the repo;
  the 130-map retail corpus the docs measure against lives in a game install. Confirm what a CI
  differential run can actually see.
- **`%+013.6f` attribution.** The 13-char zero-padded signed field is verified against
  `brush_subtract.t3d` (every field exactly 13 chars) and matches `fmt_vertex`'s construction. The
  claim that UnrealEd's exporter literally uses `%+013.6f` is **inferred** — the T3D exporter was not
  found in the public v200 source mirror.
- **`bigdecimal` `Display` thresholds** and **`dashu` scale preservation** are unverified; both only
  matter if proposal 1 is rejected.

## Sources

Internal (this repo, read in full): `old/dev/docs/board/to-plan/rewrite-uedcli-in-rust/spec.md`,
`old/dev/docs/unrealed/t3d.md`, `old/dev/docs/architecture.md` ("Coords", "The compare view vs the
identity hash"), `old/dev/docs/rationale/emit.md`, `old/dev/docs/unrealed/quirks.md`,
`old/uedcli/{model,emit,normalize,typedprops,transform,rotation,t3dtree}.py`,
`old/uedcli/propedit/base.py`, `old/uedcli/cli/{ingest.py,parsers/_arguments.py}`,
`old/uedcli/tests/fixtures/{level_small,brush_subtract,split7}.t3d`,
`old/dev/docs/board/inbox/flag-to-build-md-and-inbox-md-both-own-the-xfer/spec.md` (the 2,000,000-coord
`float`-vs-`Decimal` verification).

All measurements in §3 were run in this session against Python's `decimal` and IEEE-754 `f64`; the
scripts are not checked in.

External:

- <https://crates.io/api/v1/crates/winnow>, <https://github.com/winnow-rs/winnow> — winnow 1.0.4, release date, repo activity.
- <https://docs.rs/winnow/latest/winnow/_topic/why/index.html> — winnow's own comparison to hand-written/nom/chumsky; the "hand-written wins for small stable formats" concession.
- <https://docs.rs/winnow/latest/winnow/_tutorial/chapter_7/index.html>, <https://docs.rs/winnow/latest/winnow/error/index.html> — `ContextError`, `StrContext`, `char_span()`.
- <https://docs.rs/winnow/latest/winnow/_topic/partial/index.html> — `Partial` streaming and its re-parse caveat.
- <https://crates.io/api/v1/crates/nom>, <https://github.com/rust-bakery/nom> — nom 8.0.0, last commit 2025-08-26.
- <https://unhandledexpression.com/nom-8/>, <https://github.com/rust-bakery/nom/blob/main/doc/error_management.md> — `VerboseError` moved to `nom-language`.
- <https://crates.io/api/v1/crates/chumsky/versions>, <https://codeberg.org/zesterer/chumsky> — no 1.0; 0.13.0; `Rich`; error recovery. <https://lib.rs/crates/chumsky> is stale, do not trust it.
- <https://crates.io/api/v1/crates/pest>, <https://docs.rs/pest/latest/pest/error/index.html> — pest 2.9.2, error variants.
- <https://www.synacktiv.com/en/publications/battle-of-the-parsers-peg-vs-combinators> — nom 29.0ms vs pest 92.1ms on a line-oriented log format.
- <https://github.com/rosetta-rs/parse-rosetta-rs> — the build-time/parse-time/binary-size table (repo warns the parsers are of differing quality, so LOC is not apples-to-apples).
- <https://crates.io/api/v1/crates/logos>, <https://github.com/maciejhirsz/logos/releases> — logos 0.16.1.
- <https://docs.rs/rust_decimal/latest/rust_decimal/struct.Decimal.html> — 96-bit mantissa, `MAX_SCALE = 28`, `RoundingStrategy`, `rescale` semantics.
- <https://github.com/paupino/rust-decimal/issues/839> — `from_str_exact` Underflow parser bug.
- <https://docs.rs/bigdecimal/latest/bigdecimal/struct.BigDecimal.html>, <https://docs.rs/crate/bigdecimal/latest> — `BigInt` + `i64` scale, `to_plain_string`, `with_scale_round`, "currently being re-written".
- <https://docs.rs/fastnum/latest/fastnum/> — `Decimal<N>`, trailing zeros preserved, `quantize`, 7 rounding modes, default `HalfUp`.
- <https://docs.rs/dashu-float/latest/dashu_float/> — `DBig` context model (scale preservation undocumented → unverified).
- <https://docs.rs/fraction/> — `from_decimal_str`, Display as a ratio.
- <https://wubingzheng.github.io/en/Decimal-Crates-Comparison.html> — cross-crate perf comparison; the only source found for `decimax` and `primitive_fixed_point_decimal`.
- <https://doc.rust-lang.org/stable/src/core/fmt/float.rs.html> — Rust float `Display` is shortest-round-trip; explicit precision uses the exact formatter. **Not measured here.**
- <https://raw.githubusercontent.com/RedPandaProjects/UnrealEngine/master/Source/Engine/Inc/UnMath.h> — UE1 v200 `FVector` is `FLOAT X,Y,Z`. Third-party mirror.
- <https://raw.githubusercontent.com/RedPandaProjects/UnrealEngine/master/Source/Core/Src/UnProp.cpp> — `UFloatProperty::ExportTextItem` is `appSprintf(…, "%f", …)`. Third-party mirror.
- <https://unrealarchive.org/wikis/unreal-wiki/Vector.html> — single precision, ~7 significant digits; ±100000 UU practical map limit.
- <https://unrealarchive.org/wikis/unreal-wiki/Legacy:T3D_File.html>, <https://unrealarchive.org/wikis/unreal-wiki/Legacy:T3D_Brush.html> — block structure, the signed zero-padded vertex field, UE2 divergence. The `%+013.6f` attribution here is **inferred from output shape, not found in source**.
- <http://www.clintons3d.com/vr/T3D%20File%20Format%20Specification.htm> — 2000-era T3D spec, poly flags, CCW winding.
- <https://unrealarchive.org/wikis/unreal-wiki/Legacy:Brush_Exporting_And_Importing.html> — the importer recalculates normals; bad recalculation breaks lighting permanently.
- <https://docs.rs/unreal_asset/latest/unreal_asset/>, <https://crates.io/crates/uasset>, <https://github.com/AstroTechies/unrealmodding> — binary UE4/5 only; no text, no UE1.
- <https://github.com/EliotVU/Unreal-Library> — UELib: C#, binary UE1–3 packages, emits a pseudo-T3D view; not a parser.
- <https://github.com/crapola/blender_t3d>, <https://github.com/DarklightGames/bdk_addon>, <https://github.com/reszy/UEdConverter>, <https://github.com/mildred/t3d2map>, <https://github.com/lcultx/t3d-parser> — other-language T3D tooling.
- <https://github.com/OldUnreal/UnrealTournamentPatches/issues/430> — a 469b UnrealEd still crashes on a T3D brush with no `Model` set (importer robustness).

Unverified / could not confirm: no published LOC or effort data for a T3D-complexity grammar in any
Rust parser crate; no single maintained head-to-head article covering winnow/nom/chumsky/pest; nom's
idle period has no stated cause; `bigdecimal`'s exact `Display` thresholds; `dashu`'s scale
preservation; `decimal-rs` maintenance status; Rust's `{:.6}` byte-exactness (no toolchain here).
