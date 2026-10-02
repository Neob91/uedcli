+++
priority = "p2"
kind = "implement"
summary = "materialize post-verify false-rejects good builds over engine-stamped Actor.Base; exclude it in the compare only."
+++

# materialize post-verify excludes engine-stamped Base (compare-only)

Source: `dev/docs/spikes/levelbuild-friction/` finding #1 — its top-ranked defect ("the single most
costly defect of the run"), so a priority bump is defensible.

The engine stamps `Base=LevelInfo'MyLevel.LevelInfo0'` onto any actor resting in the level. The trunk
never authors `Base` (attachment is via `AttachTag`), so the typed post-verify compare (`_actor_values`)
sees built-`Base` against trunk-default-none and **discards a good map** — ~2.5 min per build wasted.

Ruling: exclude `Actor.Base` from the post-verify compare **only**, not the durable trunk strip.
Compare-only keeps `Base` on an imported retail actor genuinely based on a mover; a durable strip would
lose that. `BasePos`/`BaseRot` are already computed (`normalize.py`); plain `Base` is not.

Implementation: today `COMPUTED_PROPS` is stripped BOTH durably (`normalize_actor`) and in the compare
(`is_computed_key`) — one set. This needs a compare-only ignore set distinct from the durable one; add
`Base` there. Subsumed by [[derive-computed-props-from-class-schema-flags]] if that lands first.
