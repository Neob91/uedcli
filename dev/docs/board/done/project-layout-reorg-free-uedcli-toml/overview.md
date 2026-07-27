+++
priority = "p?"
kind = "unknown"
summary = "Project layout reorg: free `uedcli.toml` at the repo root + in-repo `.uedcli/` state dir"
+++

# Project layout reorg: free `uedcli.toml` at the repo root + in-repo `.uedcli/` state dir

—
BUILT 2026-07-18 (4 slices: `421b8add0` flag-day cutover + LUM migration, `e301a37cf` state-dir
threading, `3dc4c7ccb` package-relative tool assets + cwd-relative CLI paths + `repo_paths.py`
deletion, + the docs/board sweep). A project is a repo with `<root>/uedcli.toml` (root-relative
managed-dir keys, defaults `maps/`/`prefabs/`/`texture-catalog/`; `id`/`name` dropped); ALL
machine-local state in the self-ignoring `<root>/.uedcli/` (`config.state_dir`, `*` .gitignore
written on first create); tool-install assets package-relative (`tool_assets.py`); relative CLI
paths resolve against the cwd; `UEDCLI_REPO_ROOT`/`UEDCLI_PREFAB_DIR`/`UEDCLI_TEXTURE_CATALOG`
retired. Spec/plan (ephemeral): `spec.md`,
`plan.md`; durable record decisions.md 2026-07-17
20:58 UTC. The slice-2 `texture classify set` lock deviation was RESOLVED 2026-07-18: texture
flocks are catalog-adjacent `<catalog>/.locks/` (decisions.md 2026-07-18 07:53). The live
materialize/preview check PASSED (spec §10.6 — inbox record).
