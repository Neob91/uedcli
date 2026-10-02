+++
priority = "p?"
kind = "unknown"
summary = "Native class→package import resolution (§88 blocker 1)"
+++

# Native class→package import resolution (§88 blocker 1)

— BUILT 2026-07-19. Every actor class
was imported under `Engine` (`pkgref._package_of_class` called a NON-EXISTENT
`uprops.package_of_class`, always falling back to `"Engine"`), so any real level's DeusEx-package
classes (`Engine.DeusExMover`, …) made the game linker abort loading and revert to the boot map —
fatal on UNATCO/Catacombs/HK, invisible on the castle/tiny maps (genuine-Engine classes only).
Fix: `pkgref.build_class_package_index` scans the composed `.u` code set for each class's real
defining package (cross-checked against the golden UNATCO import table — all 95 real classes
match), threaded through `assemble_level(class_packages=…)` into `Resolver._package_of_class`.
NativeUnatco now imports `DeusEx.DeusExMover`/`DeusEx.ATM` (77 DeusEx + 13 Engine, zero
misclassed) and **boot-confirmed** past the class abort (loads UNATCO's real texture packages,
reaches blocker 2); castle import table + Model body **byte-UNCHANGED** (43.04% / 485 surfs /
1156 nodes / 283624 B). Regression: `test_class_package_index_resolves_deusex_classes_to_real_
packages` + `test_real_deusex_class_imports_as_deusex_not_engine`. Scoped OUT (→ inbox): closing
the 9 355 prop-skip warnings + restoring Sound/Music imports (surfaces a separate `MyLevel`
local-object-ref import defect); and blocker 2 (load-time renderer CPU loop).
