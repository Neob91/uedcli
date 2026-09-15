+++
priority = "p3"
kind = "investigate"
summary = "uscript: struct-type cast (vector(SomeRotator)) unsupported"
+++

# uscript: struct-type cast (vector(SomeRotator)) unsupported

Found compiling the real UT99 community mutator `TranslocBots` (github.com/joeytwiddle/code,
code/unrealscript/TranslocBots), `Botpack`-dependent. Real UnrealScript casts a `Rotator` to a
`Vector` (its forward direction) with `Vector(SomeRotator)` — a real, documented UE1 idiom, used
twice in this file: `vector(b.Rotation)` and `Vector(PlayerPawn(from).ViewRotation)`.

`lower._call_named` only recognises `_PRIMITIVE_TYPES` (int/float/bool/byte/string/name) and real
CLASS names as cast targets (`self.scope.is_class_name(name)`) — `vector`/`rotator` are struct type
names, neither, so this raises `LowerError(f"unresolved function {name!r}")` before even reaching
`_call_named`'s cast branches (surfaces one level up as "unresolved function 'vector'").

**Not investigated**: the real conversion opcode/mechanism. Likely a dedicated single-operand
conversion op (same shape as the existing scalar `_CONV` table, or possibly a native function call —
worth checking whether `Vector(Rotator)` compiles to a plain conversion opcode or a native call
first, live-probed against a small controlled UT99 fixture). The reverse direction (`Rotator(SomeVector)`,
not exercised by this file) would need the same treatment if it turns out to be a separate opcode.

Not landed as a corpus fixture; `TranslocBots` is otherwise close (5 small classes, `Botpack`-
dependent, no `#exec`/`.jpp` deps).
