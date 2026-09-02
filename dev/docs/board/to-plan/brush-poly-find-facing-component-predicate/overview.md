+++
priority = "p2"
kind = "implement"
summary = "`brush poly find --facing` component-predicate grammar + brush-SET input"
+++

# `brush poly find --facing` component-predicate grammar + brush-SET input

Spec written
+ **both cold-review gates passed** (findings resolved inline — the polarity-symmetry claim corrected (ALL
asymmetric predicates are flip-dependent), `visible_normal` now inverse-transpose(`actor_linear`) so it is
correct under scale/shear/reflection and unifies `list_polys`+`find_faces`, full test-migration plan):
[`spec.md`](spec.md).
Replaces `--facing`'s single geometric axis token (`+X..-Z`/`slant`, polarity-BLIND — returns a subtract
room's CEILING for `+Z`) with predicates on the face *visible normal* `(nx,ny,nz)` (`;`=AND, `:`=axis:spec,
`,`=OR, `..`=range; pose-grammar delimiters), presets `flat`/`wall`/`ramp` (polarity-free) + polarity-aware
`floor`/`ceiling`. Also makes `brush poly find` take a brush SET (`nargs="+"`/`-` stdin, dedup, warn-skip
non-brush) — addresses the single-brush note at `board/inbox/` item 5 (the geometric `--coplanar` cross-brush
find stays a separate spec). Ships a committed engine-facts regression pinning the verified subtract
normal-flip (`tests/fixtures/brush_subtract.t3d`). Drops the old axis tokens (hard break; migrates
`test_query.py`/`test_polyalign.py`/`test_cli.py`, removes the now-dead `_FACING_NEG`). Decisions:
`unrealed/t3d.md` + `direction/conventions.md`. (Andrzej, 2026-07-24.)
