+++
priority = "p?"
kind = "unknown"
summary = "`actor preview` param cleanup — `--layout`/`--frame`/`--show`, point-actor panes, optional `--out`"
+++

# `actor preview` param cleanup — `--layout`/`--frame`/`--show`, point-actor panes, optional `--out`

— BUILT 2026-07-24 (`a97573383`; suite green). The shared `cli.py::_preview_opts` helper (used by
`actor`/`stash`/`prefab preview`) went 17 flags → 13, with every hidden-interaction rule removed:
`--single`+`--breakdown` → **`--layout {quad,single,breakdown}`** (default `quad`, so mutual exclusion
is free); `--zoom`+`--zoom-region`+`--zoom-factor` → **`--frame TARGET`** (one input taking either a
`BRUSH[:IDX]` selector or an explicit six-field world AABB) + `--frame-tightness`; the three
`--show-*` booleans → one comma-set **`--show`**; `--out` made optional (a `uedcli-preview-*` temp file
is minted and its absolute path printed). `--layout breakdown` now gives each **point** actor its own
captioned pane (framed via `_point_pane_region`, expanded to at least `Location ± 32 UU` so a
zero-extent marker centres instead of jamming into a corner — regression-pinned). A **breaking CLI
change** across the three verbs; each removed spelling errored via `_RemovedFlag` with a migration
message (matching the `--class`/`--zoom-poly`/`--split` precedents). Spec `spec.md` (status corrected).
