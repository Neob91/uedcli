+++
priority = "p3"
kind = "implement"
summary = "Exact-single-node folder match (no subtree) — CLOSED 2026-08-02, owner dropped it."
+++

# Exact-single-node folder match (no subtree) — closed

Owner ruled 2026-08-02: **drop it.** A wildcard-free `--folder X` matches `X` and its whole subtree by
design (`folderlib.matches`), and no `*`/`**` glob can pin an exact node, so exact-single-node needs a
new surface (`--folder-exact` or an `=path` sigil). Judged not worth the surface — live with `--folder`
plus the globs.
