+++
priority = "p3"
kind = "debug"
summary = "AirstrikeMutator is not a valid corpus candidate"
+++

# AirstrikeMutator is not a valid corpus candidate

`AirstrikeMutator` (github.com/vumaq/ut99-mutators, the sibling repo `NoGunsMutator` came from) was
flagged in a prior session as a plausible next UT99 corpus candidate, blocked on Botpack not loading
as an `EditPackages` dependency. That Botpack gap is now fixed (see `USCRIPT-COMPILER.md`, the real
cause was Botpack's own missing bot-voice sound-package deps, not a UCC freshness-check quirk) —
`ASPMutator` (a different real mutator) landed as the corpus win it unblocked.

With Botpack now loadable, `AirstrikeMutator` was retried directly: it FAILS to compile even under
REAL UT99 `UCC.exe` (`local Rocket SpawnedRocket; ... Spawn(class'Rocket', ...)` — `Error,
Unrecognized type 'Rocket'`). Decompiling stock `Botpack.u` confirms there is no class literally named
`Rocket` — only names containing it as a substring (`RocketMk2`, `RocketArena`, `RocketPack`, …). The
source as authored on GitHub does not compile against stock UT99 at all; this is not a compiler gap,
it's a broken/mod-pack-specific source file. Not a valid corpus candidate — don't retry without a
different, real `Rocket`-declaring dependency (none identified).
