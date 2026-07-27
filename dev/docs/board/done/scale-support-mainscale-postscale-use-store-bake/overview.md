+++
priority = "p?"
kind = "unknown"
summary = "Scale support — `MainScale`/`PostScale` USE/STORE/BAKE"
+++

# Scale support — `MainScale`/`PostScale` USE/STORE/BAKE

— BUILT 2026-07-18 (plan
`plans/2026-07-18-scale-plan.md`; spec `specs/2026-07-18-scale-support.md`; decisions 2026-06-25 /
2026-07-18 14:03; spikes `2026-06-25-scale-transform-mechanics.md` +
`2026-06-25-mainscale-postscale-applytransform.md`). New `transform.py` algebra module (FScale
parse/emit, `sheer_coeff` snap, linear matrix, `bake`); scale parsed into typed `model.Actor`
fields + emitted de-duped; `rotation.actor_linear` folds `PostScale·R·MainScale` into every
world-geometry consumer + the clip/vertex inverse; `actor scale (--to|--by)`, `actor
apply-transform`, `actor rotate --to`; `MainScale`/`PostScale` in `propedit.TYPED_FIELDS`. Offline
suite green; engine-facts pin `sheer_coeff` + emission; editor-parity differential is
`test_scale_integration.py` (`-m integration`).
**Remnants (boarded elsewhere):** `--native` preview + native binary build still reject/pass-identity
scale (a separate deferred workstream — see inbox "Native materialize silently IGNORES PostScale");
the combined scale+sheer matrix ORDER (`Sheer·Scale`) is validated only by the integration
differential (single-effect cases match the live spike); no PostScale-authoring verb (`actor
post-scale` deferred); texture-lock exact vectors are integration-gated (offline asserts the L
transform, not editor bytes).
