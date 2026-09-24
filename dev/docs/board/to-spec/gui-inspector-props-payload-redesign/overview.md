+++
priority = "p2"
kind = "implement"
summary = "Redesign /scene's props payload: stop re-shipping class-constant default text per actor"
depends-on = ["gui-inspector-effective-props-search-show-all"]
+++

# GUI Inspector: `/scene` props payload redesign

Follow-up to `gui-inspector-effective-props-search-show-all` (done). Its final whole-branch review
found `/scene` ships every actor's full resolved property tree, including fully-resolved default text
for every unstated prop — ~40KB/actor measured on real content, ~32-68MB per Load on a full retail
level, most of it identical text repeated once per actor of a shared class. Owner-directed redesign
(v14 as of 2026-09-24, after thirteen design-review/correction passes — v7 switched to script-generating
every worked example from the real corpus after a hand-transcription error recurred three revisions
running; v8 extended that rule to every corpus claim in the document, prose included, after a false
prose claim about `ESheerAxis` slipped past v7's JSON-only rule; v9-v14 each fixed a handful of
remaining Important findings (wire-shape completeness, an ETag missing a version component, a missing
standalone-enum worked example, a global rename to a single uniform `default_value` field name across
every leaf kind) with no design change — every review from v9 onward found zero Critical issues):
normalize shape
everywhere — a new package-scoped, ETag-cached `GET /api/package/{package_name}/class` becomes the sole
source of a class's full prop shape (names/categories/kinds), plus that class's OWN per-property default
values (defaults are per-class, never type-shared — a shared struct type like `Rotator` has genuinely
different real defaults on different classes, e.g. `Karkian` vs `Rat`'s `RotationRate`, so only the
SHAPE, not the default text, is normalized once). Struct and enum TYPE definitions are normalized once
for shape by ONE unified mechanism, verified against the real corpus: both key on `(package, outer
class, name)`, `outer` read directly off the TYPE'S OWN export record (never the referencing property's
class) — the engine's own scoping (an export's `outer` field names its owning CLASS when
locally-declared inside a class, the owning STRUCT when declared inside a struct instead
(e.g. `Core.Scale.ESheerAxis`), or the universal `Object` root when it's genuinely global), mirroring
this codebase's existing texture-identity pattern (`Package.Group.Name`). This single rule gives the correct, already-verified
answer for the dominant case (28 real, genuinely distinct `ESkinColor` declarations a package-wide key
would wrongly collapse) AND the correct, package-qualified answer for an enum reached as a struct
member — 9 real cases found, 8 of which the OLD field-owner scheme got wrong (a bare, unqualified key).
Every real same-package struct-name collision found in the corpus (`XAIParams` ×9, three more) is
cleanly resolved by the same mechanism — no disambiguation fallback needed, closing v3's open question.
`Vector`/`Rotator`/`Scale`/`Plane`/`Color` (the structs this design centers on) DO resolve cleanly
(`Core.u`, confirmed directly, member shapes included) — a v4 claim they couldn't be found was a
tool-use bug in that pass's own investigation. `/scene` carries no shape at all, just a flat sparse
per-actor map of stated leaf paths (including `Location`/`MainScale`/`PostScale`, handled via their own
explicit rule) to their canonicalized values; the frontend renders every view (including the default
one) by walking the class shape, reading each leaf's own per-class default, and overlaying the actor's
sparse map. See `spec.md` for the full design and the v1→...→v14 change history.
