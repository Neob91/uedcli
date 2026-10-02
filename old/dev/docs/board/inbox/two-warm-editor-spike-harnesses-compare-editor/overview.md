+++
priority = "p3"
kind = "chore"
summary = "Two warm-editor spike harnesses compare editor exports with `canonical_level_hash`"
+++

# Two warm-editor spike harnesses compare editor exports with `canonical_level_hash`

`dev/docs/spikes/2026-07-18-warm-editor-materialize/harness/warm_editor_canoncmp.py:52` and
`warm_editor_probe.py:194` hash two editor exports against each other. Since 2026-07-25 00:36 UTC
that hash is pure/schema-free (no LevelInfo-name rewrite, no float32 quantization, no dropped poly
`Normal`), so those harnesses would now report round-trip noise as a real difference. They are
committed evidence for the warm-editor acceptance criterion, so they should move to
`normalize.compare_view` (which needs a `ClassDefaults`, hence a resolver — and since
2026-07-25 02:15 UTC returns typed `ActorValues`, not text) before being re-run.
(2026-07-25 00:36 UTC, cold review.)
