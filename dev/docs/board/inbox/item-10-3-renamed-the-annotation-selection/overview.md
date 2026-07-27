+++
priority = "p2"
kind = "owner-question"
summary = "Item #10.3 renamed the annotation SELECTION internals but deliberately kept \"label\" for the DRAWING machinery — the spec asked for more"
+++

# Item #10.3 renamed the annotation SELECTION internals but deliberately kept "label" for the DRAWING machinery — the spec asked for more

`LabelSpec`/`parse_label_spec`/
`DEFAULT_LABELS` became `AnnotationSpec`/`parse_annotation_spec`/`DEFAULT_ANNOTATIONS`, but
`_LabelItem`, `_PlacedLabel`, `_place_labels`, `_label_size`, `_LABEL_WEIGHTS`, `poly_labels` keep
"label", on the reasoning that a label there means one concrete text box laid out on the canvas —
annotations are decided, labels are placed. The `board/to-build/` §10.3 spec listed the drawing
machinery's prose too and justified the item with "'label' now means two unrelated things in one
codebase"; under the split a cold reader still meets "label" in `_place_labels` meaning something
unrelated to `--label`, and the codebase carries four senses in total (preview drawn text, the
actor dimension, Docker container labels in `preview_game.py`, the legend). Recorded in
`decisions.md` 2026-07-25 18:40 UTC. **Confirm the split or ask for the full rename.**
