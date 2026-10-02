+++
priority = "p3"
kind = "debug"
summary = "DONE — level import resolves the stale-package class redirect AND decodes v61 brush geometry; 8/8 retail Unreal Gold maps now import fully."
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
the retail Unreal Gold ISO: all 8 now get past the class-descent gate (none did before). The separate,
sibling gap this note used to flag as still-open — `brush_of`'s model/BSP decode never having been
extended to package v61 (Unreal Gold's map version) — is **also fixed now**
(`dev/docs/spikes/2026-09-11-unreal-gold-v61-model-format/`): `parse_model_body` gained a
`version<=61` branch (a narrower `UPrimitive` prefix + Vectors/Points/Nodes/Surfs/Verts/Polys as
separate `UDatabase` exports rather than inline arrays). With both fixes in place, `import_map` now
completes end-to-end for all 8 retail maps (re-verified 2026-09-11, no `SchemaError` on any of them).

UT99 was NOT separately re-tested (no UT99 map corpus available this session); the fix's fast path
(`index.class_exists(fqcn)` true) is a no-op when the stated package is already correct, so DX/UT99
behavior is unchanged — confirmed by the existing `mapimport.py` test suite staying green.

Regression tests: `uedcli/tests/test_mapimport_stale_class_package.py` (fast unit coverage of the
fallback logic + an asset-gated corpus sweep of all 8 maps).
