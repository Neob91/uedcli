+++
priority = "p3"
kind = "chore"
summary = "Re-measure the native-CSG mover exclusion now that the gate is schema-aware"
+++

# Re-measure the native-CSG mover exclusion now that the gate is schema-aware

`architecture.md` "World-CSG brush selection" quotes HK/UNATCO leaf-blob + zone counts measured
2026-07-19 WITH the old `*Mover`-suffix test, so the `DeusEx.BreakableGlass` brushes (4 on HK)
were still being carved into the world then. The numbers are now labelled as pre-change; re-run
`harness/build_native_hkmarket.py` + `shatter_probe.py` (both index-aware now) to refresh them —
it matters for a workstream whose bar is byte-identity with UnrealEd. (2026-07-25, cold review.)
