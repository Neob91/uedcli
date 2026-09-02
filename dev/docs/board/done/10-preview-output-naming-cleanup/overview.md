+++
priority = "p?"
kind = "unknown"
summary = "#10 Preview output + naming cleanup — all four sub-items built 2026-07-25"
+++

# #10 Preview output + naming cleanup — all four sub-items built 2026-07-25

**10.1** PNG is
now the ONLY on-disk preview form: `preview.py` still returns PPM/P6 bytes in memory (the
stdlib-only guarantee), the write boundary encodes to PNG with Pillow, `--out`'s extension is
REPLACED by `.png`, and `--png` was deleted outright. **10.2** the `_RemovedFlag` action and all 9
shims are gone (so the two older entries below that describe `_RemovedFlag` behaviour are
historical — the action no longer exists); deleting them re-opened a prefix-abbreviation hole (`--class` abbreviated into the
surviving `--class-exact`, silently restoring the exact-only footgun), so the SURVIVOR was renamed
`--class-exact` → **`--exact-class`** — load-bearing, not taste (`rationale/cli.md`, 2026-07-25 18:15
UTC; pinned by `test_parser_find_rejects_bare_class_as_unrecognized`). **10.3** the
preview-annotation internals renamed `label` → `annotation` (`AnnotationSpec`,
`parse_annotation_spec`, `DEFAULT_ANNOTATIONS`, the `annotations=` render kwarg); the drawn-text
machinery keeps "label" and both docstrings now define the two senses against the actor `label`
dimension. **10.4** every builder verb rejects a non-positive dimension through ONE shared guard
(`dispatch._POSITIVE_BUILD_DIMS` + `_check_positive_build_dims`), exit 2 naming flag and value;
#12's `extrude`/`revolve` plug in by adding one table row, enforced by
`test_every_builder_shape_declares_its_positive_dimensions`.
