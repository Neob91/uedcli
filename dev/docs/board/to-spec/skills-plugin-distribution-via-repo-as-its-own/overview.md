+++
priority = "p3"
kind = "implement"
summary = "Skills-plugin distribution via repo-as-its-own-marketplace (depends on the repo move)"
+++

# Skills-plugin distribution via repo-as-its-own-marketplace (depends on the repo move)

Ship uedcli's `claude/plugins/uedcli/` skills through the plugin marketplace (decisions
2026-07-19). **Blocked on the standalone-repo extraction above:** `/plugin marketplace add` on the current
`dx_lum` tree would clone the whole ~3.3 GB private mod repo to deliver a few KB of skills; a dedicated
small CLI repo makes distribution clean. Spec the marketplace manifest, the skills layout, and the
install/update flow once the CLI has its own repo. Interim dev install = symlink `skills/` into
`.claude/skills/`. (Andrzej, 2026-07-19; `rationale/MIGRATION.md` addendum.)
