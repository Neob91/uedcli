+++
priority = "p2"
kind = "owner-question"
summary = "The D0/D1 spec proposed level doctor --rebuilt/--built; shipped design folds both into level materialize instead"
+++

# Reconcile the bsp-issue-ground-truth-detector-d0-d1 spec with the shipped materialize BSP checks

The `to-spec/bsp-issue-ground-truth-detector-d0-d1` item's `spec.md` designs the D0/D1 detector as a
separate verb surface: `level doctor --rebuilt` (drive the editor, report drop-warning counts) and
`level doctor --built --dx <path>` (parse a saved `.dx`, locate defects).

The owner re-designed this (2026-08-03): that surface is dropped. D0 (build-output warning counts)
and D1 (built-model located defects: invisible walls + fall-through) now run automatically inside
`level materialize` after a successful build+save, advisory-only on stderr at rc 0, with
`--no-bsp-check` to disable. Shipped in `bsp-issue-detector` (see `done/`).

That spec is a separate board item, so it is not silently rewritten here. It needs the owner's call:
retire it as superseded, or keep the parts still wanted (the D0-b measurement — its own inbox item
`d0-b-measure-build-emergent-bsp-drops-over-real`; a standalone pre-built-`.dx` verb — its own inbox
item `standalone-verb-to-run-bsp-checks-on-a-pre`; the deferred D2 offline engine, largely built in
Rust already per the spec's own 2026-08-01 audit).

Also note (spec §4 stale): a `bsp/editorlog.py` now exists (promoted here); the built-model reader is
`native.umodel.parse_model_body` (reused, not re-promoted to `bsp/umodel.py`).
