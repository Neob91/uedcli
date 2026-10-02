+++
priority = "p1"
kind = "implement"
summary = "GUI: a cold (uncached) GET /scene must return within 5s on a real level; currently doesn't"
+++

# GUI: a cold (uncached) GET /scene must return within 5s on a real level; currently doesn't

Owner ruling (2026-09-15): a cold-cache `/scene` request must return within 5 seconds. A warm
repeat is already well under 1s (confirmed live on WanChai: ~0.05-0.24s, after today's payload-cache
fix, `17f701b6`) — this item is about the FIRST request after a backend restart or an explicit
`/load`, which is not yet fast enough.

**Live-profiled breakdown against the real WanChai level (2288 actors), 2026-09-15:**
- Trunk read (`trunk.read_level_with_bodies`): ~7.6-9.3s
- `resolve_actor_sprites`: ~21.8-27.4s — dominated by one native call, `read_property_tags_raw`
  (46209 calls, ~19.5s self-time, for only ~134 distinct classes — a shared-ancestor-class
  redundant-decode bug). **A fix for this specific redundancy is in progress** (dispatched
  2026-09-15, see the commit that lands under `uprops/uclass.py`/`schema_cache.py` once merged —
  check `git log --grep "read_property_tags_raw\|own_class_properties"` if this note is stale).
- `build_wireframe_payload`'s own per-actor loop: ~3.1-3.5s (already reasonable, not the bottleneck)

**Even after the `resolve_actor_sprites` fix lands, trunk read alone (~7.6-9.3s) already exceeds the
5s target on its own** — this was NOT investigated or profiled in depth this session (only
`resolve_actor_sprites` was). `trunk.read_level_with_bodies` needs its own profiling pass to find
out why reading one level's T3D tree takes multiple seconds, and whether it's fixable the same way
(a redundant/uncached decode) or is a harder structural cost (e.g. genuinely reading thousands of
per-actor files from disk).

Not yet closed: re-measure the full cold-path total once the `resolve_actor_sprites` fix lands, then
scope the trunk-read investigation as its own follow-up if the 5s target still isn't met.
