+++
priority = "p2"
kind = "implement"
summary = "Extract uedcli into its own standalone git repo (out of the `dx_lum` mod tree)"
+++

# Extract uedcli into its own standalone git repo (out of the `dx_lum` mod tree)

`direction/projects-and-config.md` already frames uedcli as a **globally-installed, generic-UE1 CLI that operates on many
independent projects, not a tool living inside one content repo** (project = any repo with a
`uedcli.toml`; tool-install assets resolve package-relative, never from a project). Its home should match
that identity — independent of the mod. Spec scope: which dirs travel (the `uedcli/` package, `bin/`,
`dev/docs/**` incl. this board + `spikes/`, the compose dir / UED22 substrate / umodel tool assets);
git-history handling (a fresh repo vs a `filter-repo`/subtree extraction of `Tools/uedcli/**` — note the
global "never rewrite published history" rule applies to the EXISTING repo, so this builds a NEW repo from
a copy, never a rewrite of `dx_lum`); how the mod repo consumes the CLI afterward (pipx install / pinned
dependency / submodule — decide); the pipx/Nuitka release story; and cutover mechanics (CI/tests, the
`dev/docs/board` pipeline, cross-repo references in `LUM/CLAUDE.md`). Prerequisite for the skills-plugin
distribution entry below. (Andrzej, 2026-07-19.)
