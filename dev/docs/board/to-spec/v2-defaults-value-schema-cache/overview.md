+++
priority = "p2"
kind = "implement"
summary = "v2 defaults-value schema cache"
+++

# v2 defaults-value schema cache

follow-up from the schema-cache v1 build (2026-07-18)` — **v2 defaults-value schema
  cache.** v1 (`schema_cache.py`, `PackageSchema`) caches only the discovery primitives; v2 adds the
  defaults-render primitives so `actor prop get`/`actor find --prop` render default VALUES buf-lessly
  (the review's HIGH-1 full fix): raw DEFAULTS blocks (`class_default_tags`), local enum tables
  (`enum_values`), per-Struct member schemas (`struct_members`), compact name/import/export tables;
  plus a NEW whole-package enum/struct enumerator (no `iter_structs`/`iter_enums` today) and
  imported-type resolution by CHAINING `load_package_schema` on the foreign package. Re-plumb the
  render consumers (`resolve_class_defaults`/`render_default_tag`/`struct_members`/`_resolve_type_
  export`/object-ref renderer) off the live `Package`/`buf`. Bumps `SCHEMA_CACHE_VERSION` + refreshes
  the frozen golden. Spec §4.1b/§4.6. Open Q (spec §9): pre-render object-refs to text at decode time
  to DROP the cached tables entirely.

---
