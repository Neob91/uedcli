+++
priority = "p3"
kind = "implement"
summary = "`packages.ensure_load` cannot detect a FAILED `OBJ LOAD` — a missing transitive content dep (e.g. `UNATCO.utx` → `CoreTexDetail`) silently renders every ref unbound (DefaultTexture bubbles)"
+++

# `packages.ensure_load` cannot detect a FAILED `OBJ LOAD` — a missing transitive content dep (e.g. `UNATCO.utx` → `CoreTexDetail`) silently renders every ref unbound (DefaultTexture bubbles)

p3. Hit live 2026-07-16 (anchor capture, minimal package dir). The
console `OBJ LOAD` is fire-and-forget; consider a post-load `Editor.log` scrape for
`Failed to load`/`Can't find file` and a named error, or a host-side `dxpkg.transitive_closure`
pre-check over the resolved load set.
