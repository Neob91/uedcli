+++
priority = "p?"
kind = "unknown"
summary = "Bug-fix bundle (unattended build #1)"
+++

# Bug-fix bundle (unattended build #1)

— BUILT 2026-07-18. Four offline fixes:
(1) `level doctor` portal-sheet false positive — `_brush_polyflags` now reads the effective flags
(actor-level `PolyFlags` OR'd with per-poly flags), so a `brush build sheet` zone-portal, whose
`PF_NotSolid|PF_Portal` live only on its polys, is skipped from watertight checks instead of
tripping phantom open-edge errors; (2) `level status`/`_git_hint` reports the edited PROJECT's own
repo, not uedcli's — returns "not a git repo" when the project only sits inside uedcli's source
tree (was leaking the tool branch); (3) `--base-name`/actor-add no longer strips trailing digits
(`Pillar1`/`Pillar2` stay distinct, not both `Pillar`); (4) XS bundle — surface-flag names
case-insensitive (`encode_flags` + `poly set` choices), `brush clip` prints a no-op message when
the plane misses the brush interior, duplicate point-actor Location warning on `actor add`, `--at`
help states it is the geometric center on every axis. All regression-tested; Python suite green.
