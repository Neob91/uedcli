+++
priority = "p3"
kind = "debug"
summary = "DONE — level import now resolves a class by name across the whole package path when the map's stated package is stale (original Unreal Gold's UnrealI vs UnrealShare); 8/8 retail maps get past the actor-class-descent gate."
+++

# Unreal1/UT99 map import: stale class-package hints (UnrealI vs UnrealShare) — FIXED

Root cause confirmed: a Gold map's import table states some classes' home package as `UnrealI`
when the shipped System files define them in `UnrealShare.u`. Genuine shipped content, not
corruption — these maps ship and play, so the real engine resolves it somehow. Working hypothesis
(unverified beyond the fix working on the whole corpus below — no DLL RE): a global by-name class
lookup, the same kind used to register native classes at boot. Needs a durable home in
`dev/docs/unrealed/package-format.md` — filed as `unreal-gold-stale-class-package-redirect-needs`.

Fixed in `mapimport._resolve_actor_class` (used by both `_is_actor_export`, the validation gate, and
`render_actor`'s property-schema lookup — the second one is load-bearing too: without it, a class
that passes the gate via the fallback still crashes moments later trying to read its properties from
the wrong package). On an exact-package miss it falls back to `ClassIndex.bare_to_fqcn()`, preferring
a `UnrealShare` candidate on an ambiguous collision (e.g. `TriggerLight`, which also exists in
`Engine`) — every observed redirect lands there.

Verified against all 8 maps (Bluff, DmDeck16, DmCurse, DmMorbias, DmTundra, Dig, Dark, DasaPass) from
the retail Unreal Gold ISO: all 8 now get past the class-descent gate (none did before). Each still
hits a separate, unrelated, already-known gap — `brush_of`'s model/BSP decode has never been extended
to package v61 (Unreal Gold's map version) — out of scope here.

UT99 was NOT separately re-tested (no UT99 map corpus available this session); the fix's fast path
(`index.class_exists(fqcn)` true) is a no-op when the stated package is already correct, so DX/UT99
behavior is unchanged — confirmed by the existing `mapimport.py` test suite staying green.

Regression tests: `uedcli/tests/test_mapimport_stale_class_package.py` (fast unit coverage of the
fallback logic + an asset-gated corpus sweep of all 8 maps).
