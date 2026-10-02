+++
priority = "p2"
kind = "implement"
summary = "uscript: static-through-instance member call (P.static.Foo()) not lowered"
+++

# uscript: static-through-instance member call (P.static.Foo()) not lowered

FIXED: `lower.py`'s `_ex_call` unwraps a `.static.` member sitting between a call's base and target
before resolving the call. Live-probed: `X.static.Method(args)` and `X.Method(args)` compile to
byte-identical bytecode. Regression `test_uscript_staticcall.py`. `IpServer` now compiles past this
line and hits a third, unrelated gap —
`dev/docs/board/inbox/uscript-cross-package-struct-type-not-resolved/`.
