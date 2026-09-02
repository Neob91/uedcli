# Spec — `Rotation` canonicalization at COMPARE time, folded against the class default

**Status:** SUPERSEDED + IMPLEMENTED-THEN-REPLACED (2026-07-25 02:15 UTC). The mechanism this spec
designs — a text fold of the `Rotation` string against the class default (`rotation.
canonical_rotation_value`), plus `normalize.contract_actor` around it — **no longer exists**: the
compare seam now decodes both sides to TYPED effective values, where a member-wise expansion against
the class default falls out of the general rule and needs no per-property fold. Kept only as design
history; read `dev/docs/decisions.md` 2026-07-25 02:15 UTC and `dev/docs/unrealed/t3d.md` "Partial struct/array
property values" for what is actually built. Ephemeral per-feature scratch; the durable record is
`dev/docs/decisions.md`. Supersedes the uncommitted first attempt described in §6.

**Read first:** `normalize.py::_prep_poly_geometry_for_canonical` / `canonical_level_hash` /
`canonical_actor_t3d`, `verify.py::_first_diff`/`verify_dx_matches`,
`rotation.py::canonical_rotation_value`, `unrealed/t3d.md` "Partial struct/array property values".

---

## 1. The bug

`level materialize` (and `level preview --game`'s internal materialize) aborts on the H3 post-verify —
writing **nothing** — for any actor carrying an axis-only rotation.

uedcli's producers write all three FRotator components:

    Rotation=(Pitch=0,Yaw=16384,Roll=0)

UnrealEd re-exports the same rotator with members equal to the class default omitted:

    Rotation=(Yaw=16384)

`Rotation` is a **raw prop string** compared verbatim, so the two spellings never converge and the
compare fails. Any yaw-only door, mover, or angled decoration hits it. Reported as inbox `[debug]`
"materialize post-verify rejects axis-aligned actor Rotation"; the workaround was to drop the
rotation. Repro: a `PlayerStart` built with `--rotate 0,16384,0` in the `basement` demo.

`Location` is immune only because it is a **typed field** (`Actor.location`) that uedcli re-emits
canonically on both sides of the compare.

## 2. The engine rule (already documented, not honoured by the code)

`MAP EXPORT` is **member-precise default-diffing**: it omits a whole property equal to the class
default AND omits individual struct members equal to the **default member** — `unrealed/t3d.md`
"Partial struct/array property values", live-confirmed 2026-07-18.

The operative word is **class default**, not zero. Offline scan of all **1346** actor classes
(`uprops.resolve_class_defaults`, 0 decode errors):

| Fact | Value |
|---|---|
| Classes that default `Rotation` at all | 1 |
| Classes with a NON-zero default `Rotation` | 1 — `TNM.LavaSpitter` `(Pitch=16384,Yaw=0,Roll=0)` |
| Classes with a NON-zero default `RotationRate` | 228 — e.g. `DeusEx.Rat` `(Pitch=4096,Yaw=65530,Roll=3072)` |

So "omit zero members" coincides with the engine rule for 1345/1346 classes and is **wrong** for
`TNM.LavaSpitter` (real, placeable, non-abstract): an author placing one unrotated makes the editor
write `Rotation=(Pitch=0)`, and a zero-based fold drops that prop entirely, so re-import resolves
`Rotation` to the class default `Pitch=16384` — the actor is silently pitched 90°. It is **silent**,
not a loud abort, because both sides fold to "no Rotation" and the post-verify then passes.

## 3. Where the fold belongs — compare time, not the trunk

`normalize.py` already draws this line. `_prep_poly_geometry_for_canonical` is documented as
"Called ONLY from `canonical_level_hash`/`verify._first_diff` — **never on durable/imported data**",
and exists because an earlier version folded round-trip-noise reduction into `canonical_actor_t3d`,
which silently float32-rounded coords and stripped `Normal` from the git-tracked trunk (cold review
caught it, 2026-07-14).

The `Rotation` spelling difference is exactly that category: **round-trip noise between uedcli's
spelling and the editor's**, carrying no authored information. It therefore folds on the **throwaway
compare copy**, alongside the float32/Normal prep.

Consequences (all of them the reason for this placement):
- The durable trunk is **never rewritten** — no migration, and authored text is preserved verbatim.
- Trunk bytes never depend on which packages happen to be installed (a class-default-aware fold
  inside `canonical_actor_t3d` would make the same trunk serialize differently per machine, and it
  is both the trunk emit AND the hash input).
- Both sides of a compare are folded in the **same process against the same resolver**, so the
  compare stays deterministic.

## 4. Design

### 4.1 The fold

`rotation.canonical_rotation_value(value, *, default)` folds an FRotator string against a default
rotator: emit a component only where it **differs from the corresponding default component**;
Pitch/Yaw/Roll order; return `None` when nothing differs (caller drops the whole prop).

- `default` is the class's `Rotation` default (`(0,0,0)` for 1345/1346 classes, and whenever the
  class is unknown to the resolver).
- Components are compared and re-emitted **textually as integers**; they are **never reduced mod
  65536**. The editor preserves over-range values verbatim — `Yaw=-131072`, `Yaw=-65536`,
  `Yaw=-81920` all occur in the retail corpus — so routing them through `parse_frotator`'s `% 65536`
  would rewrite a real rotator to zero and CAUSE the mismatch this fixes. (Comparison is on the
  integer value, so `-0` == `0`.)
- An unrecognized body (no parseable component) is returned verbatim, never guessed at.

### 4.2 Scope: `Rotation` only

Applied to the exact key `Rotation` and nothing else. `RotationRate`/`DesiredRotation` carry non-zero
class defaults on 228 classes; the same fold there is *correct in principle* but is **out of scope**
because uedcli has no producer that writes them in full-member form — the asymmetry cannot arise
today, and widening the blast radius of a compare-path change without a driving bug is not worth it.
Filed to `board/inbox/` as the general "member-diff every struct prop at compare time" follow-up.

### 4.3 Plumbing

The resolver reaches the compare path only:

- `_prep_poly_geometry_for_canonical(a)` → `_prep_for_canonical(a, *, rotation_default=…)`, or a
  sibling `_prep_rotation_for_canonical`. It is called from exactly **two** places
  (`canonical_level_hash`, `verify._first_diff`), both of which run inside a materialize/preview
  invocation that already has project context.
- `canonical_level_hash(level, *, class_defaults=None)` — an optional resolver. **Absent resolver ⇒
  every class defaults to `(0,0,0)`**, which is exactly right for 1345/1346 classes and keeps the
  pure-model callers (tests, `preview_game`'s short display hash) working unchanged.

Open question for the reviewers: whether the absent-resolver fallback should instead be a hard error
in the materialize path specifically (per `CLAUDE.md` "No silent half-answers"), so a missing
resolver can never silently reintroduce the LavaSpitter case. Recommendation: fallback for the
library default, and have `verify_dx_matches` (the post-verify) pass a real resolver ALWAYS, so the
one path where correctness matters is never on the fallback.

### 4.4 What is explicitly NOT changed

- `normalize_actor` does not touch `Rotation` (the first attempt's error — see §6).
- The three `dispatch.py` producer sites keep writing the explicit three-component form. That form is
  authored-equivalent and now compares equal; rewriting them is unnecessary churn and would not help
  hand-edited or imported trunks.
- The 4 existing trunk actors carrying the verbose form need **no migration**.

## 5. Test bar

- The reported repro: a yaw-only actor canonicalizes equal to its editor re-export (**red** without
  the fix).
- All-zero rotator vs an absent `Rotation` line compare equal on a zero-default class.
- **`TNM.LavaSpitter` fixture**: `Rotation=(Pitch=0)` against default `(Pitch=16384,Yaw=0,Roll=0)`
  is PRESERVED (not dropped) and compares equal to the editor's `(Pitch=0)`; the same string on a
  zero-default class IS dropped. This is the case that motivated the whole redesign.
- Over-range preservation: `Yaw=-65536`, `Yaw=-131072`, `(Yaw=-65536,Roll=-16384)` survive the fold.
- Scope guard: `RotationRate`/`DesiredRotation` pass through untouched.
- Engine-fact pin (`test_engine_facts.py`) against the committed editor-exported golden
  `fixtures/level_small.t3d`: every `Rotation=` omits zero components, none is all-zero, and each is
  a fixed point of the fold — i.e. normalizing never rewrites what UnrealEd itself wrote.
- The durable trunk is byte-unchanged by a hash/compare (guards the §3 regression directly).

## 6. Superseded first attempt (uncommitted)

The first implementation folded **zero-based** inside `normalize_actor`. It fixed the reported bug and
the suite was green, but it was wrong twice:

1. **Wrong rule** — "omit zero" instead of "omit == class default", silently mis-rotating
   `TNM.LavaSpitter` (§2).
2. **Wrong place** — `normalize_actor` feeds `canonical_actor_t3d`, which is the durable trunk emit,
   so it **rewrote authored trunk text** (verified: the trunk `actor.t3d` became
   `Rotation=(Yaw=16384)`) — the precise failure mode the 2026-07-14 cold review established the
   compare-time seam to prevent.

A third option considered and rejected: fold in the **producers** and migrate the 4 stale trunk
actors. Correct, but it needlessly rewrites authored files, leaves hand-edited and imported trunks
unfixed, and makes every future Rotation-writing producer a place the rule can be forgotten.
