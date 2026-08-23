+++
priority = "p3"
kind = "implement"
summary = "Done — uprops.py and propedit.py are layered packages, utexture.py's decoder half is its own module."
+++

# Refactor god modules into cohesive units

Done (`25a9325`, `689284f`, `789c103`). `uprops.py` → `uprops/` (`base` < `ufield` < `uclass` <
`values`), `propedit.py` → `propedit/` (`base` < `tokens` < `paths` < `structtext` < `fields` <
`edit`), both behind a re-export-only root so no call site changed; `utexture.py`'s BC decoders and
layout detection → `utexture_decode.py`. Largest file 1238 → 548 lines. `test_module_layering.py`
enforces the layer order and ships controls for every import spelling.

`preview.py` was left out — `consolidate-level-preview-native-onto-the-actor` is rewriting it — and
its split is tracked by `split-preview-py-after-the-preview`.
