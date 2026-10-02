+++
priority = "p3"
kind = "unknown"
summary = "A native class's own plain (non-native) property sometimes gets a spurious zero default, sometimes doesn't — real rule unknown"
+++

# Native class with a lone unset plain var gets a spurious zero default

Found live (against UED22 UCC) while writing a regression test for the `CPF_Native` fix
(`dev/docs/board/inbox/uweb-dependencies-array-over-counts-cross-class/`'s sibling work). Not one of
the six UWeb fixes; a separate, pre-existing divergence in `compile-model.md`'s "defaultproperties
block" rule ("a NATIVE or TRANSIENT class serialises only the defaults explicitly written").

## The contradiction

`WebRequest` (real UWeb, `class WebRequest expands Object native noexport;`) has several plain
(non-native) properties never set in its empty `defaultproperties {}` — `URI`, `Username`, `Password`,
`ContentLength`, `ContentType` — and NONE of them get a zero-value tag in a fresh UCC build. Matches
the documented "native = explicit-only" rule.

A minimal isolated fixture with the same shape does NOT match:

```
class CPFMixedNative expands Object native noexport;

var native int NativeVar;
var int PlainVar;

defaultproperties
{
}
```

Fresh UCC gives this `PlainVar=0` — a zero-value tag the documented rule says should be absent. Tried
and ruled out as the differentiator: an explicit `defaultproperties {}` block vs none at all (both
same); pairing the plain var with a native var (still happens); adding a native function
(`CPFNativeFunc` fixture — still happens); adding a non-native function with a body
(`CPFScriptFunc` fixture — still happens). A native class with EXACTLY ONE property (the native one,
no plain sibling) does NOT hit it.

## What's different

`WebRequest` additionally has: an enum (`ERequestType`), multiple properties (7, not 1-2), functions
of both kinds (5 native, 3 with bodies). None of these were reproduced in isolation before hitting a
budget limit on this side investigation — not chased further.

## Why not fixed here

Discovered as a side effect of a CPF_Native regression test, not one of the six real UWeb fixes this
session's commit covers. The CPF_Native regression test (`pkg_CPFNativeProbe` in
`test_uscript_package.py`) sidesteps it by using single-property classes only. Needs a live
`AllocateNameEntry`/property-walk capture correlated against WebRequest's exact shape to find the
real rule — not a guess.
