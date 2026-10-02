# Spec — `actor rotate`/`actor prop` explicit-zero `Rotation` fields vs H3 post-verify

## Goal

Decide what, if anything, is still to do about the reported bug: `actor rotate`/`actor prop`
store `Rotation=(Pitch=0,Yaw=8192,Roll=0)` (explicit zero fields); the editor re-exports
`(Yaw=8192)` (zero fields omitted); the trunk was reported to fail the H3 post-verify on its next
`level materialize`.

**Headline finding: the symptom is already fixed.** The report was filed 2026-07-16. The fix —
the typed, member-wise compare view — landed 2026-07-25, later. The proposed write-side fix in the
overview ("emit FRotator props with zero fields omitted", i.e. use `rotation.emit_frotator`) is now
**unsafe** and must not be done: it reintroduces a separate silent-corruption bug. This item is a
close-as-fixed with a regression check, not a code change.

## Current state

Two independent facts, cited to code:

1. **The write path deliberately writes all three fields, zeros included.** `actor rotate`
   (`uedcli/cli/commands/actor/edit.py:231` for `--to`, `:281` for `--by`) builds the prop with a
   plain f-string: `f"(Pitch={uu[0]},Yaw={uu[1]},Roll={uu[2]})"`. The inline comments (`edit.py:227-231`,
   `:277-281`) state this is intentional: an omitted `Rotation` re-imports as the *class default*,
   which is non-zero for `TNM.LavaSpitter` (`(Pitch=16384,Yaw=0,Roll=0)`), so dropping the prop for
   `--to 0,0,0` once built it pitched 90° with post-verify passing.
   - `actor prop set` behaves the same on the member path: `set Rotation.Yaw=8192` on an unset prop
     stores the full effective form `(Pitch=4096,Yaw=8192,Roll=0)` (base = class default merged over
     zero, every member explicit) — `uedcli/tests/test_actor_prop.py:231-239`,
     `uedcli/propedit.py:45` `STRUCT_FILL="default"`. A whole-value `set Rotation=(Yaw=8192)` stores
     `(Yaw=8192)` verbatim (`test_actor_prop.py:584`), which is already editor-identical.

2. **The compare path expands struct members member-wise against the class default.** For every
   property, each side resolves to its typed effective value: a member the text omits takes the
   corresponding class-default member (`normalize.compare_view` → `_actor_values` → `typedprops`;
   `dev/docs/unrealed/t3d.md` "Partial struct/array property values", `dev/docs/architecture.md` "The
   compare view vs the identity hash"). So `(Pitch=0,Yaw=8192,Roll=0)` and the editor's `(Yaw=8192)`
   decode to the same rotator and compare equal. This is pinned by a test named for this exact report:
   `uedcli/tests/test_normalize.py:625` `test_a_yaw_only_actor_compares_equal_to_its_editor_reexport`
   ("THE ORIGINAL REPORTED BUG").

The overview's suggested fix predates fact 2. `rotation.emit_frotator` (`uedcli/rotation.py:200`)
omits zero fields and returns `()` for an all-zero rotator, with the docstring caution "callers must
omit a wholly-zero key entirely" — using it on the write path is precisely the
drop-the-Rotation-prop bug that `dev/docs/unrealed/t3d.md` records as live silent corruption (its
numbered instance 1: "`actor rotate --to 0,0,0` … dropped the `Rotation` prop, so a `TNM.LavaSpitter`
came back pitched 90°").

## Design

**Recommendation: close the item as already-fixed, after confirming end-to-end coverage.** No
write-side or normalize change. The write side keeps emitting explicit fields (the
"never omit an actor property to mean zero" rule, `dev/docs/architecture.md`); the compare side
already makes the two spellings equal.

Options weighed:

| Option | Effect | Verdict |
|--------|--------|---|
| Close as fixed; keep explicit-field writes; add/point-to a regression | No behavior change; matches the landed convention | **Recommended** |
| Omit zero fields on the write path (`emit_frotator`) | Reintroduces the `TNM.LavaSpitter` drop-the-prop corruption for the identity case; violates the write-side rule | Rejected |
| Reduce/normalize `Rotation` mod 65536 or to a canonical spelling in `normalize` | Over-range components must stay verbatim (`Yaw=-131072` ≠ unrotated); a mod would collapse 20,109/23,960 corpus components to zero | Rejected |

The only real work is verifying an end-to-end regression exists — a full `actor rotate` (or
`actor prop set`) → `level materialize` → H3 post-verify pass for a yaw-only actor. The unit test at
`test_normalize.py:625` proves the compare equivalence directly; if no verb-to-materialize test
covers the same path, add one (below). That is a test-only addition, not a fix.

## Edge cases & errors

- **`--to 0,0,0` / a `--by` composing to identity** — must still write explicit
  `(Pitch=0,Yaw=0,Roll=0)`, never drop the prop (the `TNM.LavaSpitter` case). Current code already
  does; pinned by `test_normalize.py:633` (explicit all-zero == absent for a zero-default class) and
  `:883`-ish (LavaSpitter: explicit zero ≠ absent). Any "fix" that omits fields breaks these.
- **Over-range components** (`Yaw=-131072`, `65536`) — compared verbatim, never reduced mod 65536
  (`test_normalize.py:645`). No change.
- **Case-insensitive key** — a hand-edited `rotation=(...)` compares as `Rotation`
  (`test_normalize.py:658`). No change.
- **`actor prop set Rotation.Yaw=`** on an unset prop — fills from the class default, not zero
  (`test_actor_prop.py:231`), so a non-zero-default member (`DeusEx.Rat` RotationRate) is not
  silently zeroed. Handled by the same typed compare. No change.

## Tests

- Existing, already pinning the fix: `test_normalize.py::test_a_yaw_only_actor_compares_equal_to_its_editor_reexport`
  and its siblings (`:633`, `:639`, `:645`, `:658`); `test_typedprops.py:109`.
- **Add only if missing:** one end-to-end regression that runs `actor rotate --to 0,16384,0` (and/or
  `actor prop set Rotation.Yaw=8192`) on a real fixture, then `level materialize`, and asserts the H3
  post-verify passes — closing the loop from the verb's stored `(Pitch=0,Yaw=16384,Roll=0)` to the
  editor's `(Yaw=16384)` re-export. `test_rotate_integration.py` / `test_materialize_verb.py` are the
  homes. If such a path is already exercised by an existing materialize corpus test, cite it in the
  close-out and add nothing.

## Open questions

One owner confirmation (below): agree to close as already-fixed, no write-side change.
