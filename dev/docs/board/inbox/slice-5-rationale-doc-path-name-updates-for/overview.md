+++
priority = "p3"
kind = "docs"
summary = "Slice 5: rationale doc path/name updates for moved parser converters"
+++

# Slice 5: rationale doc path/name updates for moved parser converters

The scalar converters moved from `cli/main.py` to `cli/parsers/_arguments.py`, and the `docs` parser
registration moved to `cli/parsers/docs.py`. Mechanical accuracy edits made (per the slice-5 task's
dev/docs directive; the plan's approval gate listed these files):

- `rationale/cli.md`: `cli.parse_decimal` -> `parse_decimal`; Refs path
  `uedcli/cli/main.py (parse_decimal/parse_coord/parse_bbox/parse_pan)` ->
  `uedcli/cli/parsers/_arguments.py (...)`.
- `rationale/surface.md`: link+names `uedcli/cli/main.py parse_pan/parse_factor_pair` ->
  `uedcli/cli/parsers/_arguments.py ...`.
- `rationale/reported-coordinates.md`: `cli.parse_coord` -> `parse_coord`.
- `rationale/userdocs.md`: Refs `uedcli/cli/main.py (the docs parser)` ->
  `uedcli/cli/parsers/docs.py (...)`.

No prose meaning changed. `architecture.md` deliberately untouched (handled separately per the plan).
