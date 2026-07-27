+++
priority = "p1"
kind = "debug"
summary = "Native real-level LOAD — blocker 2 remaining (blocker 1 FIXED 2026-07-19, §88)"
+++

# Native real-level LOAD — blocker 2 remaining (blocker 1 FIXED 2026-07-19, §88)

A native build of any REAL level (UNATCO/Catacombs/HK) does NOT reach the "5.5-min CPU hang" — it
used to **fast-fail** first on ~~blocker 1~~ (now fixed). **~~Blocker 1: every actor class imported
under `Engine`~~ — FIXED 2026-07-19:** `pkgref.build_class_package_index` scans the composed `.u`
set for each class's real defining package (threaded into `Resolver._package_of_class`), so
`DeusExMover`→`DeusEx.DeusExMover` etc. (77 DeusEx + 13 Engine class imports on NativeUnatco, zero
misclassed). Boot-confirmed: the `Can't find Class Engine.DeusExMover` abort is gone; the load now
reaches blocker 2. Regression in `tests/test_native_materialize.py`. (Closing the 9 355 prop-skip
warnings + restoring Sound/Music imports was scoped OUT — it surfaces a separate `MyLevel`
local-object-ref import defect; see the two follow-up chores below.) **Blocker 2 (behind it, the
original hang, HARDER): a single-thread CPU loop in the software-renderer path during load.** With
imports corrected, the map clears linking then spins ~92 % CPU forever, frozen before "Bringing
Level up for play". `winedbg` puts the spinning thread in `deusex`-mainloop → `extension` →
`engine` render → `softdrv`/`core`/`windrv::BitBlt` (NOT the linker/GC). Reproduces WORLD-ONLY
(no DeusEx actors); the BSP is structurally sound (no cyclic/bad indices) — so it's the software
renderer looping on the over-split/over-zoned WORLD during the load-time frame draw (an
`OccludeBsp`-class pathology; ties to the §84 +33 % over-split / §70 20-vs-7 over-zoning lanes) or
possibly a world-texture-reference defect (124 vs 133 tex imports, some group-less). Next test
(§88 §7): small-world-subset vs full (renderer-BSP) and single-base-texture rebuild (texture).
Evidence + reproduce: `sections/88-native-load-hang.md` + `harness/{load_hang_probe.sh,
build_native_unatco_variant.py,build_native_unatco_qualified.py,bsp_health_check.py}`. (Found +
root-caused 2026-07-19; supersedes the "UNATCO load-hang" framing in the older board notes below —
the hang is real but sits BEHIND blocker 1.)
