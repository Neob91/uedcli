+++
priority = "p2"
kind = "implement"
summary = "uscript: byte -> string conversion (string(SomeByteVar)) not lowered"
+++

# uscript byte -> string conversion missing

Found compiling the real UT99 `IpServer` package (`USCRIPT-COMPILER.md`'s corpus survey): `GetPlayer`
reads `P.PlayerReplicationInfo.Team` (a `byte`) through a `$` string concat, which lowers a `string()`
cast — `lower.py`'s `_CONV` table has no `("byte", "string")` entry, so `_coerce` raises `no
conversion 'byte' -> 'string'`.

The exact opcode is unconfirmed — probing it (a controlled `local byte B; S = string(B);` fixture
against a live UED22 UCC compile, same method as the `assert`/`EX_ObjectToString` fixes in
`USCRIPT-COMPILER.md`) was blocked this session by host-wide docker/OCI resource exhaustion
(`resource temporarily unavailable`, `procReady not received`), not by anything about the fix itself.
`int->string` is `0x53`, `bool->string` `0x54`, `float->string` `0x55`, `object/class->string` `0x56`,
`name->string` `0x57` — byte may chain through `byte->int` (`0x3A`) then `int->string`, or have its
own direct opcode; needs the live probe to settle, not a guess.

Sources + a fresh UT99-UCC golden for `IpServer` are saved (not committed, scratch) at
`_scratch/uscript_survey/IpServer/` in the `agent-aa2a8ccb8c9c77994` worktree, if still present.
