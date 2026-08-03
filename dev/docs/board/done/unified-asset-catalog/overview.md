+++
priority = "p2"
kind = "implement"
summary = "One catalog engine over texture, class, sound and music; spec re-gating after two rounds of structural findings."
depends-on = ["native-texture-decode"]
+++

# Unified asset catalog — one engine, four kinds

DONE (texture arm, 2026-08-03). The `texture` noun ships list/show/preview/search/classify·set·unset·
status·tags/prewarm over the composed path, keyed by the frozen `sha256(w,h,RGB)` content identity
(procedurals name-keyed), with masked/group as Layer-2 facts, colour pre-fill, and refuse-then-`--force`
`classify set`; the legacy manifest subsystem (`texture sync`, `uedcli/texture.py`) is deleted. The
class arm shipped earlier; audio (`sound-corpus-remeasure`) and the shared-engine pieces (derived
index, preview pool, `classify prune`/rekey — `texture-classify-rekey-and-prune`) remain their own
board items. Follow-ups filed: `fold-sprites-are-ordinary-textures-ruling-into` (owner-gated doc),
`texture-prewarm-force-is-a-no-op-today`.
