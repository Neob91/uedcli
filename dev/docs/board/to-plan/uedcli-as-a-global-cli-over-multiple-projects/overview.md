+++
priority = "p1"
kind = "implement"
summary = "uedcli as a global CLI over multiple projects (config + projects + layered assets)"
+++

# uedcli as a global CLI over multiple projects (config + projects + layered assets)

**BIG PRIORITY.** Spec + **plan** written, both cold-reviewed (findings folded):
`specs/2026-06-29-…-design.md`, `plans/2026-06-29-…-plan.md`. **Foundation BUILT + tested +
reviewed** (commits `817bdc42b`, `0eec5f293`): slice A pyproject/pipx (also fixes the `PIL` bug),
slice B `config.py` (39 tests, unwired → suite green). **Remaining slices C–H DEFERRED/GATED** —
see `board/inbox/` (slice C needs a `packages.py` consumer refactor; 2 open decisions:
migration, container mounts). Original spec ref:
`spec.md`. Turns uedcli from a repo-bound tool into
a `pipx`-installed CLI operating on many project dirs. Core: tool/substrate/project/session
**separation**; **two config files** — `~/.uedcli/config.toml` (per-user base substrate, ABSOLUTE
colon-glob `paths=`) + `<project>/uedcli.toml` (project overlay, RELATIVE globs + a uuid `id`);
**layered resolution** (project shadows base; `--explain-paths`); **central per-project state**
`~/.uedcli/projects/<id>/{store,locks,tmp,shots}` (sessions move OUT of the content tree — apply
still writes the `.dx`/T3D artifact INTO it); **content-addressed texture store**
`~/.uedcli/textures/{packages/<pkg-hash>.<schema>/index.json, data/<pixel-hash>.png}` (dedup +
explicit `texture gc`). Replaces hardcoded `substrate_search_dirs` + `host_repo_root`; new verbs
`project init/ls/rm`, `config`, `texture gc`. **GATED on 3 decisions for Andrzej (spec §10):**
(1) base-catalog cross-machine sharing — moving the base catalog to per-user `~/.uedcli/` is a
**sharing regression** vs today's tracked/committed catalog; (2) migration carry-vs-drop of
in-flight sessions; (3) overlay container-mount strategy (programmatic `docker run` bridge vs
decontainerize-first). Resolve those, then plan — likely sliced: **(a) pipx packaging** (also fixes
the `No module named PIL` host-interpreter bug — self-contained, do first), (b) project/config
resolution + `uedcli.toml`/`config.toml`, (c) content-addressed texture store, (d) container overlay.
**⚠ STALE — re-spec before building.** The 2026-06-29 spec behind this predates three superseding
decisions and must be reconciled first, not built as-written: (1) **no project `id`, no central
`~/.uedcli/projects/<id>/` state, no session store** (2026-07-05 in-tree-state / git-trunk / no-id
decisions — `direction.md`); (2) **`project init/ls/rm` reduce to `project show`** (name→id
registry + uuid minting are gone); (3) the **project-layout reorg** — free `uedcli.toml` at the repo
root + in-repo gitignored `.uedcli/` for throwaway state + free relative tracked dirs — now BUILT
and closed out (2026-07-18; `board/done/` tail): decisions.md 2026-07-17 20:58 UTC (no scaffold verb —
`project` stays `project show` only; tool-install assets go package-relative, and how they ship
under pipx/Nuitka belongs to THIS item's re-spec). Re-spec against current `direction.md` +
`architecture.md` before planning.
