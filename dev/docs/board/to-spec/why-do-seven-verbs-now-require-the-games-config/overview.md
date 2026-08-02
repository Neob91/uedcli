+++
priority = "p2"
kind = "implement"
summary = "Why do SEVEN verbs now require the games config? Investigate what each one actually needs mover-ness FOR, then scope the requirement back"
+++

# Why do SEVEN verbs now require the games config? Investigate what each one actually needs mover-ness FOR, then scope the requirement back

Making `movers.is_mover`
schema-aware (`direction/conventions.md`, 2026-07-25 10:18 UTC — "one predicate, no split") propagated the
class-resolver requirement to every call site: **`mover key`, `level doctor`, `event graph`,
`stash capture`, `brush scale`, `brush apply-transform`, `brush intersect`/`deintersect`** now
exit 2 without a project + `~/.uedcli/config.toml`. (`level materialize` and both `level preview`
tiers already required one.) Andrzej's ruling only sanctioned it for `level doctor`; the other six
came along as a consequence, and that is a wider user-facing narrowing than the question asked
about.
**Investigate first, decide second.** Per call site, answer with evidence from the code: (a) *why*
does it ask the mover question at all; (b) what would the verb do differently if it simply did not
ask; (c) is the answer load-bearing for correctness, or only for an optimization/warning. A verb
in class (c) can stop asking, which drops its resolver requirement with no fallback and no second
predicate. Suspect cases worth checking first: `brush intersect`/`deintersect` were **pure
stdin→stdout filters** needing no project at all before this, and `event graph` resolves mover-ness
before its skip so it fails on a class with no `Event`/`Tag` that it would have ignored anyway.
**Same decision owns the second flag:** the predicate also hard-fails on any actor whose class is
off the composed search path — stricter than "no games config", so a trunk ingested from a retail
`.dx`, or a mod actor whose `.u` sits elsewhere, now fails verbs that used to produce a report.
Both resolve as one scoping call: *which verbs may skip the mover question entirely.*
**Also in scope — the ONE surviving name-suffix mover test, `preview.classify_brush`.** It still
decides mover-ness with `bare.endswith("Mover")`, on the shared `actor preview` / `stash preview` /
`prefab preview` path, where it picks the CSG palette's magenta *mover* colour. (It also feeds
`is_solid` for hidden-line removal, but `"mover"` and `"add"` are both solid there, so usually only
the colour differs — unless the misclassified mover carries `CsgOper=CSG_Subtract` or
`PF_NotSolid`, which also costs it its solidity.)
It was deliberately NOT threaded with the index, because doing so would add a further
verb family to the resolver requirement this very item is trying to scope back — the same
decision, so it is answered here rather than pre-empted. Today it diverges from `mover key` /
`level doctor` on exactly the classes the schema-aware predicate was written for
(`CaroneElevatorSet.CEDoor`, `DeusEx.BreakableGlass`/`BreakableWall`, `TNM.Barricade`, and —
`endswith` being case-sensitive while UE1 `FName`s are not — `TNM.fanmover`/`platformmover`/
`weakmover`): they render as ordinary additive brushes. Whatever the scoping call is, this
function must come out of it with ONE answer: either it takes the index (and `*preview` joins the
resolver-requiring set), or preview is ruled a class-(c) "cosmetic only" caller and the name test
stays with that written down as a deliberate, documented approximation. `architecture.md`
"Mover support" and the `classify_brush` docstring both record it as pending this item.
**Ruled out in advance** (`direction/conventions.md`, 2026-07-25 10:18): a name-suffix fallback, an optional
resolver that silently degrades, and a second divergent predicate. The only sanctioned fix is
scoping. Outcome is a superseding entry in `direction/conventions.md` — the current
"Explicit, discoverable, model-side" bullet names all seven verbs and would need rewriting.
(Andrzej, 2026-07-25; consequence of `board/to-build/` #9.4.)
