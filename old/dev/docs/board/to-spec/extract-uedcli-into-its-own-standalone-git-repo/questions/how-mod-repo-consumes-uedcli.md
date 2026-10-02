# How does the dx_lum mod repo consume uedcli now that it lives in its own repo?

## Context

uedcli is now standalone (`github.com:Neob91/uedcli`). The mod repo it used to contain it must now
reach it somehow. Options:

- **pipx global install + a `uedcli.toml` in the mod repo (recommended).** Matches
  `direction/projects-and-config.md` exactly — "one globally-installed CLI that operates on many
  projects"; the mod becomes just another project identified by its `uedcli.toml`. No vendored copy,
  no submodule to keep in sync.
- **git submodule** — pins a commit, but re-introduces uedcli source inside the mod tree (the thing
  extraction removed) and needs manual bumps.
- **pinned dependency** (pip/pipx from a git ref or tag) — decouples source but couples the mod's
  environment to a uedcli version; needs a release cadence.
- **fully decoupled** — the mod holds nothing; developers install uedcli themselves.

This is outward-facing (it changes how the mod repo is set up and how collaborators install), so it
is the owner's call. It also gates the downstream `skills-plugin-distribution-via-repo-as-its-own`
item.

## Answer

<!-- Empty = open. -->
