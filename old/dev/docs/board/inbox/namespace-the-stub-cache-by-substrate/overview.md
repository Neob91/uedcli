+++
priority = "p?"
kind = "unknown"
summary = "Namespace the stub cache by substrate"
+++

# Namespace the stub cache by substrate

(`.uedcli/cache/stubs/` → e.g. `.../stubs/deusex/`, or
key it by substrate id). Stubs are inherently substrate-specific (the v68→v69 DeusEx conversion);
separating them per-substrate aligns with the generic-UE1 direction (per-substrate, no DeusEx
baked into shared paths) and avoids cross-substrate name clashes if a second substrate is ever
added. Touch points: `config.stub_cache_root`, `packages._stub_cache_dir` /
`substrate_search_dirs`, the `/stubs` bind-mount, cache-key/migration. Surfaced 2026-06-26 (Andrzej).
Small but has a substrate-identity design angle — triage to `to-spec`/`to-build` accordingly.
