+++
priority = "p3"
kind = "chore"
summary = "~30 backticked citations name spec files deleted long before the board migration; no test sees a dead prose path, so they rot silently."
+++

# ~30 citations name specs that were deleted before the board migration

Found while sweeping citations of the 98 specs and plans that moved into board items. These are a
*different* set: they name spec files that were already gone at `9c0f787^`, before that work
started — specs deleted when their feature landed, in some cases with the doc saying so
("landed; spec deleted"). Verified with `git cat-file -e 9c0f787^:dev/docs/<path>` on a sample; all
came back missing.

Roughly 30 sites, including `uedcli/dxpkg.py`, `stub.py`, `stub_cache.py`, `stub_closure.py`,
`surface.py`, `t3dtree.py`, `trunk.py`, `texture_catalog.py`, `uscript_rewrite.py`, `builders.py`,
four files under `uned/`, `dev/docs/unrealed/commands.md` and `quirks.md`, several spike findings,
and five board items citing `specs/2026-07-25-unified-asset-catalog.md` (the pre-split unified spec,
now three separate arm specs).

**Not fixed here, deliberately:** they are pre-existing rot, not caused by the spec-and-plan move,
and each needs a judgement about what the durable replacement is — usually a section of
`architecture.md`, `unrealed/*.md` or a `rationale/` topic, occasionally nothing at all. A
mechanical sweep would have to invent those targets.

**Why nothing catches them.** `test_doc_links.py` checks markdown links and, in prose, only paths
into `direction/`, `rationale/` and `rules/` — the trees the docs restructure retargets at. A
backticked `specs/…md` in a docstring is invisible to every check in the suite. Widening the prose
check to `dev/docs/**` would catch this class permanently; that doc's own comment explains why the
scope was kept narrow (a blanket rule flags ~150 legitimate references), so widening needs the
exclusions worked out first.
