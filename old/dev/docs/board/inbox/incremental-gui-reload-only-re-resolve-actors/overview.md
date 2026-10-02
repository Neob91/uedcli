+++
priority = "p2"
kind = "implement"
summary = "GUI Reload re-resolves every actor from scratch every call; owner wants <1s by diffing changed actors against the session's last-loaded snapshot"
depends-on = ["gui-reload-rebuild-slow-memoize-scene"]
+++

# Incremental GUI Reload: only re-resolve actors that changed since last Load

Owner-raised (2026-09-28). `uedcli serve`'s Reload (`POST /api/session/{id}/load`,
`uedcli/serve/app.py`'s `session_load`) unconditionally re-reads the whole trunk and re-resolves
every actor's sprite/mesh/mover render data from scratch on every call -- measured to cost the same
whether or not anything actually changed (real levels: ~4.7s at 487 actors, ~14.4s at 2288 actors,
identical on a second call with zero trunk edits). The owner's expectation: a typical edit touches a
handful of actors (one changed, a couple added/removed), and Reload should cost hundreds of ms, not
scale with the whole level.

`gui-reload-rebuild-slow-memoize-scene` (done) already removed the class-schema-rebuild part of the
cost that's independent of actor count. What's left is genuinely per-actor work that only an
incremental diff can avoid.

**Feasibility read (not yet designed):** plausible, and not unprecedented -- `TrunkLevelSource.save`
already does the mirror-image diff on the write side (content-diff via `read_level_with_bodies`
against the process's own load snapshot, only writing actors whose body/rank changed;
`architecture.md`'s "core write pattern"). Reload would need the same idea in the read direction:
keep the session's last-loaded per-actor bodies, diff current trunk bodies against them next Reload,
and only re-resolve the added/changed/removed set.

**Real blockers, not just "write a diff":**
- `_LoadedTrunk`'s tables (`sprite_table`, `mesh_polys`, `mover_polys`, `mover_texture_table`, ...)
  are flat lists built by iterating ALL actors in one pass -- splicing in one changed actor needs
  these keyed/mergeable by actor name instead, real restructuring.
- Texture indices are shared/deduped across actors by table POSITION. Removing/adding one actor's
  entries without shifting every other actor's stored index needs a stable per-texture-ref registry
  (keyed by content, not position).

Needs a spec before planning -- the table/texture-index restructuring is the crux design question,
not the diffing itself. Not spiked or scoped yet.
