+++
priority = "p3"
kind = "debug"
summary = "UT99 UCC make treats Botpack as needing rebuild when used as an EditPackages dep"
+++

# UT99 UCC make treats Botpack as needing rebuild when used as an EditPackages dep

Found chasing a `NoGunsMutator` candidate (landed as a corpus win without needing this — see
`USCRIPT-COMPILER.md`). `_edit_packages_upto`'s `deps` mechanism (`reference_ut99.py`) already works
for `UWindow`/`IpDrv` as prebuilt stock deps (no `Classes/` dir, no rebuild) — `UWeb`/`UscInheritFinal`/
`UscIpAddrProbe` all rely on it. `Botpack` does not: adding `EditPackages=Botpack` (with or without
every other stock package that precedes it in the CD's own list) makes `UCC.exe make` fail:

```
--------------------Botpack--------------------
Analyzing...
Can't find files matching ..\Botpack\Classes\*.uc
Exiting due to error
```

Ruled out: a case mismatch between the fetched filename (`BotPack.u`, from `fetch_ut99.sh`) and the
ini's own `EditPackages=Botpack` spelling — this host's filesystem is case-insensitive (`cp
BotPack.u Botpack.u` reports "same file"), so that's not it.

Not chased further — `NoGunsMutator`'s `Mutator` superclass lives in `Engine` (confirmed against
`github.com/Slipyx/UT99/blob/master/Engine/Mutator.uc`, a decompiled stock UT99 tree), not `Botpack`,
so no dependency on this was needed. Left open because a future candidate that genuinely needs a
`Botpack`-declared class (e.g. `TournamentGameInfo`, `Enforcer` as an actual class ref rather than a
bare `Name` literal) will hit this. Next step: a live UCC capture of `UMakeCommandlet::Main`'s
freshness check to see why it treats `Botpack.u` differently from `UWindow.u`/`IpDrv.u` — not attempted
here (out of scope for the change that found it).
