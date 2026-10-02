+++
priority = "p3"
kind = "implement"
summary = "uscript: same-class-typed param Context under-counts Dependencies"
+++

# uscript: same-class-typed param Context under-counts Dependencies

Found building a regression fixture for the `.static.` call fix
(`dev/docs/board/done/uscript-static-through-instance-member-call-p/`, closed): a class with a
LOCAL param typed as the SAME class (`function int Foo(UscStaticThroughInstance P) { return
P.Bar(5); }`, a self-typed instance, not `Self`/`Super`) compiles to a class body 18 bytes smaller
than a fresh UED22 UCC build of the identical source -- a `Dependencies` array with 2 entries where
UCC's has 4.

`lower.py`'s `_record_dep` skips recording a Context's class dependency when the base type's class
name equals the compiling class's own name or its super's name (the assumption: a self/super
reference already carries its own `deep=1` entry, so a `deep=0` one would be redundant). That
assumption holds for an IMPLICIT self-reference (an unqualified call inside the class, which never
goes through `_record_dep` at all -- it's `_call_named`, not `_call_method`) and for explicit
`Self`/`Super`. It does NOT appear to hold for an ordinary local/param typed as the class's own
type (`P: UscStaticThroughInstance`) referenced via a genuine Context -- real UCC still records
entries there our skip drops.

Not investigated further (found as a byproduct, out of scope for the `.static.` fix). No fix
attempted. The regression test for the `.static.` fix (`test_uscript_staticcall.py`) works around
this by comparing decoded FUNCTION bytecode directly rather than the whole-package `gate()`, so it
isn't blocked on this bug -- but it means that fixture's own class-level body is NOT byte-exact
against golden, worth knowing if someone later expects it to be.
