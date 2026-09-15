+++
priority = "p3"
kind = "implement"
summary = "scene.py's _class_category_map has the same redundant per-descendant class-schema decode the sibling fix closed elsewhere, currently masked by the default-on schema cache"
+++

# scene.py's _class_category_map has the same redundant per-descendant class-schema decode the sibling fix closed elsewhere, currently masked by the default-on schema cache

Found by review (2026-09-15) of commit `a2d97a85` ("Cache per-class own-props decode in
resolve_class_properties"). That fix closed the redundant-decode bug for `ClassDefaults`-seeded
callers (`resolve_actor_sprites`), but `uedcli/serve/scene.py::_class_category_map` (used by
`build_wireframe_payload`, the inspector-categories feature) calls `resolve_class_properties` with
neither `_cache` nor the new `_own_cache` — the exact same per-descendant re-decode pattern.

Currently masked in practice because the persistent per-package `schema_cache` (a separate,
already-existing memo) covers this path when enabled, which is the default. Measured with the
schema cache forced OFF: this path cost 43.7s of a 51.15s `build_wireframe_payload` call on WanChai
(785 `own_class_properties` calls, 44633 native decode calls) — more expensive than the path
`a2d97a85` fixed. With the schema cache on (default), it collapses to ~4s.

Not urgent while the schema cache stays on by default, but the two call sites will drift further
apart the more each grows its own caching story. Worth folding `_class_category_map` onto the same
`_own_cache` mechanism (or confirming a good reason not to) as a small follow-up.
