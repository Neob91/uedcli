+++
priority = "p?"
kind = "unknown"
summary = "Class-default contraction at the compare seam + the write side stops omitting to mean zero — BUILT 2026-07-25 00:36 UTC"
+++

# Class-default contraction at the compare seam + the write side stops omitting to mean zero — BUILT 2026-07-25 00:36 UTC

UnrealEd omits what equals the CLASS DEFAULT; uedcli tested
against ZERO. Fixed in four parts: (1) `normalize.contract_actor` (fed by `classdefaults.ClassDefaults`)
contracts BOTH compare sides against the real class defaults — whole property, `Rotation` members,
`Location`, and the editor's `Tag=<class>` default-stamp (the last only where the class does not
itself default `Tag`, since `TNM.Trestkon` defaults `Tag='Player'`); (2) `canonical_level_hash` is
now PURE and schema-free (it is the preview build-CACHE KEY) with the post-verify moved to a
separate `normalize.compare_view`, which `verify._first_diff` also consumes (the duplicated
reduction is gone); (3) class defaults resolve BEFORE the editor container exists, `defaults` is a
REQUIRED no-fallback argument of `verify_dx_matches`, and an unresolvable class exits 2 naming the
actor; (4) four write paths stopped omitting a property to mean zero — `actor rotate --to/--by`,
`brush build --rotate`, `normalize_actor`'s all-zero `Location` clear and its `Tag` strip, and
`transform.bake`'s `PrePivot` drop. Three of those were SILENT wrong-map bugs that post-verify
passed. Two cold reviews resolved. `unrealed/t3d.md`
"Partial struct/array property values"; `architecture.md` "The compare view vs the identity hash".
**SUPERSEDED 2026-07-25 02:15 UTC** — the contraction MECHANISM (parts 1's `contract_actor` and
its helpers) was replaced by the typed effective-value compare above, which also closed both of
this item's remnants; parts 2-4 (the pure identity hash, the no-fallback up-front resolution, and
the write-side rule) stand.
