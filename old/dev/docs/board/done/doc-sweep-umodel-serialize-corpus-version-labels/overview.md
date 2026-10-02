+++
priority = "p?"
kind = "unknown"
summary = "Doc sweep: UModel-serialize corpus version labels"
+++

# Doc sweep: UModel-serialize corpus version labels

— DONE 2026-07-19. The `parse_model_with_zones`
→`parse_model_serial` half was ALREADY done (quirks.md already correct; the old symbol exists nowhere
but the board). The v69→v68 half rested on a WRONG premise: on-disk the corpus is MIXED (105 v68 + 15
v69 in DeusExAssets/Maps; original-shipped = v68, UnrealEd-2.2-rebuilt = v69), and the `UModel::Serialize`
Model-body format is IDENTICAL across the v68↔v69 bump (researched: v68/69 differ only header-level —
heritage-table→generation-info at 68, minor UT99 increment at 69). So relabeled the spike doc +
`test_umodel_serialize.py` as **v68–v69 (format version-stable)**, not bare v68 or v69. Commit `9699c9699`.
