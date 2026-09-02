+++
priority = "p?"
kind = "implement"
summary = "Store-centric model (UnrealEd as a build/preview tool)"
+++

# Store-centric model (UnrealEd as a build/preview tool)

— IMPLEMENTED
2026-06-18 (offline suite green). The session store's model-side T3D is authoritative; `apply`
reads THEIRS offline, ensure-loads the manifest, materializes (full re-import), post-verifies
against the INTENDED result (H3); `level open`/`create`/the open-gate are gone, replaced by
`session start [<dx>]` + `package load`. Folds in `export_and_qualify` and
`dxpkg.transitive_closure`, live-verified 2026-06-20. See `architecture.md`,
`unrealed/quirks.md`, `direction/trunk-and-editor.md` (2026-06-18). (Open follow-ups tracked in `board/to-spec/`.)
