+++
priority = "p?"
kind = "unknown"
summary = "Generator-flag cleanup: `--folder`/`--label` move to the generators; ditch `--group`"
+++

# Generator-flag cleanup: `--folder`/`--label` move to the generators; ditch `--group`

— BUILT
2026-07-24 (`22f82b8a8` code + `960275b0d` docs; suite green). Three parts, all shipped: (1) `--folder`
+ repeatable `--label` added to the `brush build` shapes and `actor build` (they emit the existing
`// uedcli-folder:`/`// uedcli-labels:` carriers); (2) both flags REMOVED from `actor add`, which is now
a **pure carrier-consumer** (post-hoc organization = `actor folder set` / `actor label`) — an explanatory
comment at the `actor add` parser records why; (3) `--group` dropped from `brush build` in favour of
`--prop Group=`. The two surviving `--group` flags are out of scope and intentionally kept (`prefab/stash
place`'s placement group, `actor find --group`'s engine-prop filter). REVERSES the folder/label-on-`actor
add` rule; `direction/organization.md` + `direction/generators.md` ("Folders"/"Labels"/"Generator pattern") reconciled, `docs/usage.md` updated,
tests migrated (`test_generators.py`/`test_folders.py`/`test_labels_verbs.py`/`test_cli.py`). Coupled
prerequisite for the native `intersect`/`deintersect` item (still in `board/to-plan/`), which shares
`brush build`'s output-flag set. Decision `direction/organization.md` (2026-07-24 17:04 UTC); spec
`spec.md` (status corrected).
