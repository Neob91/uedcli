+++
priority = "p3"
kind = "owner-question"
summary = "DONE 2026-08-27. Participation and radius are no longer a heuristic: the rule is disassembled (LightType != LT_None && (bStatic || bNoDelete), Editor 0x100a4cc7/0x100a4cd4) and every value is read as the EFFECTIVE one through classdefaults, which is the CDO read this item asked for."
+++

# N-4 light participation + radius are a HEURISTIC (no CDO read) — resolved

Both halves are closed.

**The CDO read exists.** `native.materialize.gather_lights` resolves `LightType`, `LightRadius`,
`bStatic`, `bNoDelete` and `bSpecialLit` as EFFECTIVE values through `classdefaults.ClassDefaults` —
the value the actor states, else the class default decoded through the property's declared type. The
"missing `LightRadius` defaults to 64" guess and the "carries a light prop or is a `*Light` class"
fallback are both gone. A stated value that will not decode now raises `LightPropError` naming the
actor, the property and the text rather than reading as absent.

**The participation rule is disassembled, not guessed.** The editor's gather pass accepts an actor on
`LightType != LT_None` AND `(bStatic || bNoDelete)` (`Editor 0x100a4cc7` / `0x100a4cd4`), with no class
check at all. The second condition is what the heuristic was missing: it is why the editor's bake
lists none of `03_NYC_UNATCOHQ`'s (mislabeled `01_NYC_UNATCOHQ` until 2026-08-31) 7
`DeusEx.SecurityCamera`s even though they default
`LightType=LT_Steady` — `DeusEx.DeusExDecoration` overrides `bStatic` back to False and nothing in
their chain sets `bNoDelete`.

Measured against the editor's own `LIGHT APPLY` of the UNATCO trunk: the set of light actors listed on
at least one surface is 189 on both sides, 0 only-native and 0 only-editor.
