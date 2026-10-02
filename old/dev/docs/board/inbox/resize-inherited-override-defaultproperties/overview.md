+++
priority = "p3"
kind = "investigate"
summary = "uscript: overriding an INHERITED property's default in defaultproperties drops its name"
+++

# uscript: overriding an INHERITED property's default in defaultproperties drops its name

Found compiling the real UT99 community mutator `Resize` (github.com/joeytwiddle/code,
code/unrealscript/Resize) during the uscript-compiler corpus campaign. `Resize expands Mutator` and
its `defaultproperties` block overrides four properties it does NOT declare itself, all inherited
from `Actor`:

```
bAlwaysRelevant=true
NetPriority=3.0
NetUpdateFrequency=10
RemoteRole=ROLE_SimulatedProxy
```

Our compile succeeds (no exception) but the resulting name table is missing exactly these four
names (`header name_count`: 138 vs golden's 142; `name-table CONTENT` diff lists exactly
`balwaysrelevant`, `netpriority`, `netupdatefrequency`, `remoterole` as golden-only) — the
`defaultproperties` tags for these four overrides are silently absent from the compiled `.u`.

Not the same gap `UscEnumDef`/`RemoteRole=ROLE_SimulatedProxy` already covers — that fixture is a
SINGLE inherited-enum override with nothing else in the block; `Resize` has FOUR inherited overrides
together (a bool, two floats/ints, and the enum), so either the multi-override case specifically
breaks, or `RemoteRole` alone isn't actually what `UscEnumDef` pins (worth rereading that fixture
before assuming it's covered).

**Not investigated further** — `Resize` also has two more divergences once this is fixed (both look
like separate, smaller Line/TextPos-or-jump-target-by-one-or-two bugs in `AlwaysKeep`/`ScaleActor`,
not yet root-caused): `EXPORT[12]`(?)-style script-size mismatches of 1-2 bytes, same symptom shape as
the `MessageAdmin`/`ArenaFallback` fixes this session (a downstream jump target off by a small
constant), but a different root cause since those two are already fixed. `Resize` itself is
`Botpack`-dependent (`Translocator`); parked, not landed as a corpus fixture.

**Next step**: build a controlled fixture isolating ONE inherited-property override (not enum) in a
class with an EMPTY own declaration list, live-probe against UT99 UCC, compare to `UscEnumDef`'s own
shape to find what differs when there are multiple overrides in one block.
