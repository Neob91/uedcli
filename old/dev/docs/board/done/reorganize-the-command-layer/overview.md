+++
priority = "p2"
kind = "implement"
summary = "Split CLI parsing and command orchestration out of the two composition hotspots"
+++

# Reorganize the command layer

Done. `cli.py`/`dispatch.py` split into the `uedcli/cli/` package: `main` (parser assembly),
`dispatch` (routing + the ordered process-error guard, ~167 lines), `parsers/` (one registrar per
family), `commands/` (one owner per family; `actor`/`brush` are packages), and the cross-family
owners `errors`/`resources`/`level_sources`/`ingest`/`targets`/`rendering`/`placement`/`generators`.
Behavior-preserving; parser characterization fixtures, the AST boundary test (rules 1–9 incl. no-SCC)
and the route/family-isolation matrix enforce it. `architecture.md`'s module-map update is proposed
separately for owner approval (board owner-question).
