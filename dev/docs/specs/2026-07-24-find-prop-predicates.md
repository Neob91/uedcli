# `find --prop` predicates — comparison operators, glob match, existence

**Status: UNFINISHED / PARKED (2026-07-24)** — do not build. Part of the "find extra filters" effort
that Andrzej put on hold; the §8 sub-choices are unresolved and the whole thing awaits his direction.
The design below is review-clean (two cold passes — typed-field seam, `_validate_query_value`, numeric
parse, `~=` dependency all folded), but it is NOT approved to sequence. Ephemeral — fold into
`usage.md` + `architecture.md` if/when built. **Code refs symbol-anchored** (lines drift).
**Decisions ledger:** append on confirmation of the §8 sub-choices.
**Extends** the `find --prop` EQUALITY matcher (spec `2026-07-18-actor-prop-subcommands.md`, §7).
Sibling of `2026-07-24-find-spatial.md`; **relational** is a deferred board item. Adds richer ATOMS to
the composable-`find` boolean model.

---

## 1. Motivation

`find --prop KEY=VALUE` matches only **exact equality** on the effective value (`propedit.effective_match`).
So `Health>50`, `Name` contains `torch`, or "is this explicitly set?" are inexpressible. This adds three
predicate forms to the SAME `--prop` token, keeping equality the default. **In scope:** comparison
(`> >= < <= !=`), glob (`~=`), existence (bare `KEY`). **Out of scope:** regex (a later toggle), relations.

## 2. Grammar — a NEW parse entry point (the existing one can't be reused)

`find` currently calls `propedit.parse_token(t, expect_value=True)`, which splits on the first `=` — so
`Health>50` → "expected KEY=VALUE" and `Health>=50` → base `Health>` → bad-ident error. **A separate
`parse_match_token` is REQUIRED** (not "a new mode" of the value parser); `actor prop set|unset|get`
keep calling the unchanged `parse_token`, so their grammar is byte-for-byte unaffected.

`parse_match_token` scans a **left-anchored key-path run** `[A-Za-z0-9_.]+` (the existing dotted
base+segments), then reads the **maximal operator** immediately after it — one of
`= != > >= < <= ~=` (longest-match: `>=`/`<=`/`!=`/`~=` win over `>`/`<`/`=`) — and the rest is the value:

- A bare key-path with **no operator** → the **existence** form (`op="exists"`, `value=None`).
- `PropToken` gains **`op: str` (default `"="`)**; the set/get callers never populate it.
- Values may contain `=`/parens/quotes (a struct `(X=1,Y=2)` still parses — the OP is located at the
  first non-key character, and the paren-index form is already rejected upstream, so no `(` can precede
  the OP).
- **Transposition guard:** `Health=>5` / `Health=<5` parse as OP `=`, value `>5` — detect the `=>`/`=<`
  prefix and emit `did you mean >=/<=?` rather than a downstream "can never match."

## 3. The predicate forms, and the TWO matcher seams

`effective_match` has **two dispatch paths**, and BOTH must become op-aware:

1. **Typed fields** (`Location`, `MainScale`, `PostScale` — `TYPED_FIELDS`) dispatch to
   `TypedField.match`/`ScaleField.match` **before** any schema/value logic. Today those `assert
   tok.value is not None` and do **equality only** — so as-is, `--prop Location` (existence) would
   **traceback** and `--prop Location.X>50` would silently do `==`. **Both matchers must take `op`**:
   numeric compare on an axis leaf (`Location.X>50`), reject a comparison OP on the **whole vector**
   (`Location>50` → named error), `~=` over the rendered text, and existence (see §3.3). No `assert` on
   a None value.
2. **Schema props** flow through `resolve_path` → `effective_value` → the comparison, gated by
   **`_validate_query_value`** (which today rejects "can never match" values). That validator sits in
   the modified path and must branch on `op`: equality/`!=` keep it; numeric OPs require a numeric token
   (reject non-numeric, `nan`/`inf`); `~=` accepts any text (skip the "never match" reject); existence
   takes no value.

### 3.1 Operators & type rules
| OP | Meaning | Valid on | Wrong kind → |
|----|---------|----------|--------------|
| `=`  | equality (unchanged canonical-scalar compare) | any | — |
| `!=` | logical NOT of `=` (**but see §3.4** — an actor whose class lacks the key is NOT matched) | any | — |
| `> >= < <=` | numeric compare | **scalar** numeric leaf: `IntProperty`, `FloatProperty`, **resolvable-enum-free** `ByteProperty` | exit 2 naming the prop + kind |
| `~=` | flat `*`-only glob over the effective text, case-insensitive | text-ish leaves (§3.2) | exit 2 (or §8.2) |
| *(none)* | existence — the key is explicitly STORED (§3.3) | bare base (§3.3) | — |

- **Numeric compare parses BOTH sides uniformly as `Decimal`/float** for all numeric kinds — do NOT
  split int-vs-float (the existing `_canon_scalar` already parses Int/Float/Byte via `float`), so
  `Health>5.5` on an `IntProperty` is a valid bound, not a reject. `nan`/`inf` tokens → exit 2.
- **Scalar-leaf only:** a whole static array (`array_dim>1`, no index) renders as a tuple
  `(0=..,1=..)` while `leaf.kind` is still the element kind — a numeric OP must **reject** it (as `=`
  already special-cases the tuple), named error: match one element with `Foo.N>5`.
- **Enum vs numeric byte keys on RESOLVABILITY:** `ctx.enums(prop)` returns `()` for a plain byte AND
  for an *unresolvable imported* enum, so an unresolvable-enum byte is compared as an ordinal — note
  this (the split is "has resolvable enum names," not "has a type_ref").

### 3.2 `~=` scope (footgun control)
`~=` matches the effective **text**. For `Str`/`Name`/`Object`-ref/enum-name leaves that's exactly
right (`Name~='*torch*'`). For **struct/array/object** leaves the text is internal canonical formatting
(`(X=0,Y=0,Z=0)`, member order, default-fill) — a glob there matches the *rendering* and silently
shifts if the canonical form changes. **Recommend: restrict `~=` to text-ish leaf kinds**
(`Str`/`Name`/`Object`/enum-name), exit 2 on struct/array. *(Sub-choice §8.2: restrict vs allow-any
with a documented-fragile caveat.)*

### 3.3 Existence — bare base only, stored-present
`_stored_map(actor)` is keyed `(casefold(base), index)` — it knows base names + array indices, **not
struct members**. So existence is defined for a **bare base with no dot-path** (`--prop Health`); a
dotted existence (`--prop Nest.Marks`) → exit 2 ("existence takes a bare property name"). Semantics:
the key is **explicitly stored** on the actor (authored; present in `_stored_map`), NOT merely having an
effective value. **`KEY` (exists) vs `KEY=` (effective value equals empty string) are different** —
document it in help (for most `StrProperty`s `KEY=` matches nearly everyone; `KEY` matches only
authors). **Typed-field existence** (`--prop Location`): a typed field is intrinsic (always on the
model), so it has no `_stored_map` entry — define existence there as **always-matches** (recommended),
NOT a stored-map miss that says "never." *(Sub-choice §8.1.)*

### 3.4 `!=` is NOT equivalent to composable-`find` `--exclude`
`effective_match` returns `None` when the actor's class doesn't declare the key → no-match. So
`--prop X!=1` does **not** match actors whose class lacks `X`, whereas `find --prop X=1 --exclude -`
over a universe **includes** those actors. Over heterogeneous class sets they differ — a good reason to
keep `!=` (it's not mere sugar). Document + test the asymmetry: "an actor with no such prop is not
matched by `!=`."

## 4. Composition (unchanged, and noted)

**Repeated `--prop` is AND-within** (`ok = ok and r` in the find handler) — UNLIKE the OR-within
membership filters (`--label`/`--folder`/`--group`), because each `--prop` is a distinct **constraint**,
not a value of one set. This spec keeps that. Same-dimension OR over props → the composable-`find` union;
NOT-a-prop → `--exclude` (mind §3.4). Cross-filter AND (`--prop … --folder …`) unchanged.

## 5. Module shape / touchpoints

- **`uedcli/propedit.py`** — `PropToken.op: str` (default `"="`); a NEW `parse_match_token` (§2);
  `effective_match` dispatches on `op` across BOTH seams (§3); `TypedField.match`/`ScaleField.match`
  gain an `op` param (numeric per-axis, whole-vector-compare rejected, `~=`, existence — no `assert` on
  None); `_validate_query_value` branches per op (§3). The set/get/`actor prop` callers pass no op —
  unaffected.
- **A shared FLAT glob helper** — `*`-only, `casefold`+`fnmatchcase`, reject `?`/`[`/`]`. **This does
  not exist yet** (the actor-labels `labellib` is unbuilt; `folderlib` is dotted/globstar). Put it in a
  neutral module (`textmatch`/`glob`) that whichever of {this spec, actor-labels} lands first
  introduces and the other reuses; do NOT cite a not-yet-built `labellib` symbol. *(Sequencing
  sub-choice §8.4.)*
- **`uedcli/cli.py`** — the `find --prop` help documents the operator grammar (`KEY=V | KEY!=V | KEY>V
  | KEY>=V | KEY<V | KEY<=V | KEY~=GLOB | KEY`). No new flag.
- **`uedcli/dispatch.py`** — the `find --prop` block calls `parse_match_token`; the AND-within loop,
  typo protection, and `SchemaError` handling are unchanged.

No model/trunk change.

## 6. Errors (each names the offending value, exit 2 — never a traceback)

- comparison OP on a non-numeric / whole-array / whole-struct leaf; a non-numeric or `nan`/`inf` token
  with a numeric OP; `~=` on a struct/array leaf (per §8.2) or a `?`/`[` in the pattern; a dotted
  existence key; the `=>`/`=<` transposition hint; an unknown key on all considered classes (existing
  typo-protection); typed-field existence-vs-operator misuse (whole-vector compare). **Existence on a
  typed field must NOT `assert`** — it returns a boolean.

## 7. Test strategy (host-native `bin/test`)

1. **Comparison (schema prop):** `Health` 10/50/90 → `>50` only 90; `>=50` 50+90; `<50` 10; `!=50`
   10+90; boundary + equal; `Health>5.5` on an Int prop is VALID (uniform Decimal parse).
2. **Typed field:** `Location.X>50` numerically compares the axis; `Location>50` (whole vector) → exit
   2; `Location` (existence) → boolean, no traceback; `MainScale.Scale.X>=2`.
3. **Type guards:** `>` on Str/Bool → exit 2 naming the kind; `Health>abc`/`Health>inf` → exit 2;
   numeric OP on a whole static array → exit 2.
4. **`~=` glob:** `Name~='*torch*'` substring, `Torch*` prefix, case-insensitive; `?`/`[` → exit 2;
   struct/array `~=` per §8.2 (restricted → exit 2, or the fragile-rendering pin).
5. **Existence:** an actor that stores `Health` matches `--prop Health`; one on the default does not;
   `--prop Location` always matches (typed intrinsic); `--prop Nest.Marks` (dotted) → exit 2.
6. **`!=` asymmetry (§3.4):** an actor whose class lacks `X` is NOT matched by `--prop X!=1`.
7. **Composition + regressions:** repeated `--prop` ANDs; `actor prop set Health=50`/`get` still parse
   with NO operator (the shared-`parse_token` regression); maximal-munch (`Health>=50` → op `>=`, not
   base `Health>` op `=`).

Use artificial values (`1337`, `Health=50`, `Torch_ab12`).

## 8. Open sub-choices for Andrzej

1. **Existence semantics** — bare-base "explicitly STORED" (recommended) vs "differs from default";
   and typed-field existence = always-matches (recommended) vs error "not meaningful."
2. **`~=` scope** — restrict to text-ish leaves (recommended, avoids the struct/array rendering
   footgun) vs allow-any-with-documented-fragility.
3. **`!=` — keep** (recommended; NOT `--exclude` sugar per §3.4) vs drop and rely on `--exclude`.
4. **Sequencing of the flat glob helper** — introduce it in THIS spec (neutral module) and have
   actor-labels reuse it, or land `~=` AFTER labels and reuse theirs? (Only affects `~=`; the
   comparison operators have no such dependency.)
5. **Split existence out?** (reviewer scope suggestion) — existence queries the stored map (a different
   animal from effective-value compare, and it collides with typed fields/deep paths). Keep it here
   restricted to bare-base (recommended — small), or spec it separately and ship comparison + `~=` first?

## 9. Docs to update on build

- **`docs/usage.md`** — the `find --prop` operator grammar + examples (incl. `KEY` vs `KEY=`).
- **`architecture.md`** — the `--prop` matcher dispatches on `PropToken.op` across both seams.
- **`decisions.md`** — append the resolved §8 sub-choices.
