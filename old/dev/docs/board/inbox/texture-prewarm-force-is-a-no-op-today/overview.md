+++
priority = "p3"
kind = "owner-question"
summary = "texture prewarm --force is a no-op today (conventions vs plan)"
+++

# texture prewarm --force is a no-op today (conventions vs plan)

`texture prewarm` decodes every texture on the path, warming the resolver's ref→identity cache. That
cache is per-INVOCATION (each CLI call is a fresh process), so there is no persistent state for
`--force` to refresh — `_run_prewarm` never reads `args.force`. As shipped, `--force` is an accepted
flag that does nothing.

`conventions.md` forbids no-op flags. But the texture-arm plan (T6) and spec (§4) explicitly list
`prewarm [--force]`, anticipating the deferred content-addressed preview POOL — once that lands,
`--force` would re-render cached previews. So the flag is intentional-but-premature, not an accident.

Implemented as the plan specifies (the flag is registered and accepted) rather than dropped, per
"implement the decision as given". Flagged for the owner: keep `--force` reserved for the preview
pool, or drop it until the pool lands (the strict no-no-op-flag reading). Not resolved here.

Also filed alongside: `texture prewarm` itself only warms a per-process cache today, so it is
near-inert until the persistent preview pool / derived index lands — same deferred dependency.
