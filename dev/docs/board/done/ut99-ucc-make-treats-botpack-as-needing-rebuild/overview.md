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

## FIXED — misdiagnosed as a freshness-check quirk; the real cause is a missing content dependency

Chasing the real community mutator `ASPMutator` (`github.com/rxut/AdvancedSpawnPoints`, needs
`TournamentPlayer`/`UTTeleportEffect`/`TeamGamePlus`, all `Botpack` classes), reproduced the exact
`Can't find files matching ..\Botpack\Classes\*.uc` failure and captured the FULL `UCC.log`, not just
stdout's tail. The real sequence: `Warning: Failed to load 'Female2Voice': Can't find file for package
'Female2Voice'` → `Warning: Failed to load 'Botpack.u': Can't find file for package 'Female2Voice'` →
THEN `Analyzing...`/the Classes-dir error. `Botpack.u` itself references several bot-voice `Sound`
packages in its own `#exec AUDIO IMPORT`s (decompiled and grepped for `Sound'Pkg.Name'`: `Announcer`/
`BossVoice`/`Female1Voice`/`Female2Voice`/`Male1Voice`/`Male2Voice`) — when ANY of them can't be
found, `Botpack.u` itself fails to LOAD as a prebuilt binary, and UCC's `make` then falls through to
trying to ANALYZE/compile it from source (which has no `Classes/` dir either) — hence the misleading
error. The sound packages live on the CD's `Sounds/` directory (`Paths=../Sounds/*.uax` in the ini),
not `System/` (where `fetch_ut99.sh` only ever fetched), so they were never on the search path at all.

Fixed: `fetch_ut99.sh` now also fetches those six `.uax` files into `uned/UT99/Sounds/`;
`reference_ut99.ut99_sounds_dir()` validates their presence (same pattern as `ut99_substrate_dir()`);
`ut99_container` mounts `uned/UT99/Sounds/` directly at `/opt/UT99/Sounds` (read-only, no copy step —
nothing writes into it). With this, `Botpack` loads as a prebuilt dependency exactly like `UWindow`/
`IpDrv` always did — no UCC freshness-check special-casing was ever real. `ASPMutator` is now a real
corpus win (`USCRIPT-COMPILER.md`), and the fix is substrate infra any future Botpack-dependent
candidate gets for free.
