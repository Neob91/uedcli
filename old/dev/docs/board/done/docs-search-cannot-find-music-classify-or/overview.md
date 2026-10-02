+++
priority = "p1"
kind = "docs"
summary = "docs search cannot find `music classify` or `prefab list`/`drop`"
+++

# docs search cannot find `music classify` or `prefab list`/`drop`

Fixed by the `usage.md` split (`dev/docs/superpowers/specs/2026-08-30-usage-md-split-design.md`):
`docs/reference/music.md` now spells `music classify set/unset/status/tags` explicitly, and
`docs/reference/prefab.md` carries a plain, unbroken `prefab list`/`prefab drop` mention alongside
the accurate `--prefab-dir`-first synopsis form.
