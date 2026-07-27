+++
priority = "p1"
kind = "debug"
summary = "A Tag whose value is a single space is not round-trip stable, so an imported retail tree churns on 20 of 88 maps."
+++

# A `Tag` whose value is a single SPACE is not round-trip stable, so an imported retail tree churns on 20 of 88 maps

`retail 02_NYC_Street`'s `Teleporter3` carries such a `Tag`.
The canonical emitter writes it as `Tag= ` (bare, trailing space); re-parsing that yields `Tag=`, so
`canonical_actor_t3d ∘ parse_t3d` is not a fixed point for that one actor — 1 of 2060 on that map,
but it fails the corpus sweep's stability check on 20 maps. **This is an `emit`/`parse_t3d`
whitespace asymmetry, not a decoder bug** — the decoder faithfully reproduces a name the map really
stores. Fix belongs in the emit/parse pair (quote a whitespace-only name, or refuse it at ingest);
until then the corpus sweep is red on those maps. Found 2026-07-27 by sweeping the retail corpus.

*Carried over from the `installer-url` branch, whose `inbox.md` addition the board migration had already deleted.*
