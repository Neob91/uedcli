# `is_placeable` is fail-open, against conventions.md "a predicate answers or it RAISES" — pick one

## Context

Not in the spec's §8, and that is the gap: the earlier class spec
(`the-asset-catalog-class-arm-needs-four-changes/spec.md`) flagged this decision, but the standalone
spec's §1 reuse table silently reuses `classindex.is_placeable` labelled "(fail-open)" without carrying
the unresolved call forward.

`classindex.is_placeable` (uedcli/classindex.py:206) is
`descends_from(fqcn, Engine.Actor) and is_abstract(fqcn) is not True` — so a class whose abstractness is
**undeterminable** counts as placeable. That is a "don't know" answered as a confident yes, which sits
directly against `direction/conventions.md` (lines 64, 193): "**A predicate answers or it RAISES.**
'Don't know' is never returned as `False`" — and by the same reasoning must not be returned as a
confident `True` either. The `--include-abstract`/`placeable` axis, `class list`, and
`classify status`'s denominator all rest on this predicate.

- **Options (from the earlier spec):** (a) state the fail-open behaviour plainly in the `--help`, or
  (b) make the undeterminable case raise. Do not ship help text that promises a clean "non-abstract,
  descends from Actor" while the predicate quietly fails open — that is the stale-help failure
  conventions.md names.
- **Direction default:** conventions.md points at (b) — a predicate raises on "don't know"; but
  fail-open was a deliberate "list it rather than hide it" choice, so the owner should pick.

**Recommendation:** the owner picks (a) or (b) and the chosen behaviour is pinned by a test. Whichever
is chosen, correct the `is_placeable` / `--include-abstract` help to state what the predicate actually
does.

## Answer

<!-- Empty = open. -->
