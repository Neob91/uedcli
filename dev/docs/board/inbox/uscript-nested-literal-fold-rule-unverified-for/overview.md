+++
priority = "p3"
kind = "investigate"
summary = "uscript: nested-literal fold rule unverified for unary-wrapped binary operands"
+++

# uscript: nested-literal fold rule unverified for unary-wrapped binary operands

Found in code review of the `PubliciseScore`/`PainSoundsMutator`/`NoobJuice` round's nested-literal
constant-fold fix (`lower._ex_binary`'s `_NESTED` sentinel — a numeric literal nested inside either
binary operand never folds, live-probed on two shapes, both nesting under an OUTER BINARY operator).

`_ex_unary` still calls `self.expr(e.children[0])` with no `expected`/`_NESTED` propagation, so a
binary sub-expression nested under a UNARY operator (e.g. `-(4 * FRand())`) always folds its constant
operand, unlike the same nesting one level under another binary operator (already fixed). If real
UCC's true rule is "never fold a non-outermost operand" regardless of the enclosing operator kind —
plausible given the `_NESTED` evidence — this diverges for the unary-wrapped case.

Not fixed here — no live probe covers this specific shape, and the `_NESTED` mechanism's own comment
already concedes the general invariant isn't fully understood; guessing at the unary extension risks
the same "unverified generalisation" mistake caught elsewhere this round. Needs a live UCC probe of
`-(4 * FRand())` or equivalent against a known-`int`/`float` assignment target before touching it.

**Update (2026-09-14):** a SEPARATE, more severe bug in this same mechanism was found and fixed while
re-verifying the full suite after this review: `_ex_binary` propagated `_NESTED` to its children
UNCONDITIONALLY, even when its OWN `expected` was `None` (an untracked context — a function-call
argument), silently stopping folding in the already-known-open call-argument gap and breaking the
previously-byte-exact `ExtendedBuilders`. Fixed (`nested = _NESTED if expected is not None else
None`) — see `USCRIPT-COMPILER.md`'s `PubliciseScore`/`PainSoundsMutator`/`NoobJuice` row and its
"Testing" section note. This item's own unary-wrapped-binary question is UNAFFECTED by that fix and
remains open.
