+++
priority = "p1"
kind = "implement"
summary = "BSP-issue ground-truth detector = D0 + D1 (the complete detector on the real editor build); D2 = optional fully-offline upgrade"
+++

# BSP-issue ground-truth detector = D0 + D1 (the complete detector on the real editor build); D2 = optional fully-offline upgrade

Full design (3-round-reviewed):
`specs/2026-06-24-uedcli-offline-bsp-engine-design.md`; decision: `decisions.md` 2026-06-24 12:40
UTC (revises 09:07). Five grounding spikes (`spikes/2026-06-24-*bsp*` / `*offline-bsp-engine*`)
hold the decoded substrate. **(Also in `to-build.md` #1.)**
- **D0 DONE + validated** (`spikes/2026-06-24-offline-bsp-engine-d0-editorlog.md`): `bsp_editorlog.py`
  parses the editor's `MAP REBUILD` drop-warnings — caught an injected open-box hole live.
  **Next:** **D0-b** — run it over the repo's real DeusEx maps (needs gitignored install content)
  to measure build-emergent vs single-brush hole frequency; then promote `bsp_editorlog.py` →
  `uedcli/bsp/editorlog.py` with offline golden + integration tests and a `level doctor` verb.
- **D1 (next):** **P0-a** — feasibility of a binary `UModel` parser for the saved `.dx` built model;
  then `report.analyze_built` LOCATES HoM/T-junction cracks, invisible-wall phantom nodes,
  fall-through. D0+D1 = complete detector.
(D0/D1 use the live editor once per check — NOT fully offline. The shipped static `level doctor`
is the fully-offline per-brush tier; D2 below is the fully-offline build-emergent tier, deferred.)
