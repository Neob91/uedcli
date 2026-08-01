+++
priority = "p3"
kind = "implement"
summary = "class arm C0 (schema_cache v2 persists class defaults) not built by C1"
+++

# class arm C0 (persist resolved class defaults) — not needed by C1, needed before C2/list --json

The class-arm spec lists **C0** as a prerequisite: `schema_cache` v2 should persist resolved class
defaults so cold runs stop re-resolving defaults corpus-wide (~14.6 s measured). C1 was told to build
C0 **only if C1 needs it**.

C1 (`class show <one class>`) does **not** need it: a per-ref show resolves defaults only for the
named class's own super chain (a handful of packages), not corpus-wide. Measured interactively it is
sub-second offline. So C0 was **deliberately skipped** for C1.

C0 is still needed before the slices that resolve defaults across the whole corpus — `class list
--json` and `class preview` (C2), and any `prewarm`. Note `SCHEMA_CACHE_VERSION` is already 2 and the
props blob exists; C0 adds a **defaults** blob beside the disc/prop blobs, bumps the version, and
refreshes the frozen golden (`test_schema_cache`).
