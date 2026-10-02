# Pivot-cross RE harness (2026-09-18)

Scripts and captures used to reverse-engineer UED22's real pivot-cross (`GPivotShown`/
`GPivotLocation`) mechanism, and to live-drive/screenshot both real UED22 and this GUI's own app for
verification. Findings live in `GUI-PARITY.md`'s "Pivot-cross multi-select rendering..." section, not
here -- this is the raw tooling, kept for reuse on adjacent UED22 mechanisms.

Rough map (no strict pipeline order -- these accumulated across several investigation rounds):
- `*.py` -- disassembly/static-analysis scripts (call-site enumeration, vtable/IAT reads, string
  cross-references, flag/property scans) against `uned/UED22/Editor.dll` and related binaries.
- `*.sh` -- drivers for booting a throwaway UED22 container, sending real clicks/console commands,
  and capturing screenshots.
- `*.t3d` -- small test-level fixtures used during live capture.
- `s*.png`/`c*.png` -- captured screenshots from various rounds.
- `SelectionMarkers.new.tsx` -- a working draft of the eventual `SelectionMarkers.tsx` fix.

No committed regression pins this harness's own findings directly -- those are pinned by
`web/src/scene/SelectionMarkers.test.tsx`/`selectionSet.test.ts` in the main codebase instead. Treat
this directory as reusable tooling, not a source of truth on its own; if `GUI-PARITY.md`'s findings
and this harness's scripts ever disagree, the doc is authoritative and this harness is stale.
