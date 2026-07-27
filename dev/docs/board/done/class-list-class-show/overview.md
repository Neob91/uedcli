+++
priority = "p?"
kind = "unknown"
summary = "`class list`/`class show` — orthogonalize the overloaded `--all`"
+++

# `class list`/`class show` — orthogonalize the overloaded `--all`

— BUILT 2026-07-19 (`7b7664a67`),
surfaced 2026-07-24 as untracked-DONE work in a board audit (it was built directly, never on the board;
spec header was stale at "draft"). `--all` split into `--include-non-actor` (E1 reroot
`Engine.Actor`→`Core.Object`), `--include-abstract` (E2 show abstract/non-placeable), and `--depth N|all`
(E3 depth, unified spelling on both verbs; `all`→`math.inf`, uncapped); hidden `--all` emits a targeted
split-hint. Defaults unchanged; tests migrated (`test_class_discovery.py`/`test_ingest_validation.py`,
green). Spec `specs/2026-07-18-class-flag-orthogonalization.md` (status corrected), decision
`decisions.md` 2026-07-19.
