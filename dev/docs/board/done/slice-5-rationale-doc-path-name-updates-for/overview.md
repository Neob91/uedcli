+++
priority = "p3"
kind = "docs"
summary = "Slice 5: rationale doc path/name updates for moved parser converters"
+++

# Slice 5: rationale doc path/name updates for moved parser converters

Mechanical path/name accuracy edits in `dev/docs/rationale/` (`cli.md`, `surface.md`,
`reported-coordinates.md`) after the scalar converters moved `cli/main.py` -> `cli/parsers/_arguments.py`
and the `docs` parser registration moved to `cli/parsers/docs.py`; no prose meaning changed.
`architecture.md` deliberately untouched (handled separately per the plan).
