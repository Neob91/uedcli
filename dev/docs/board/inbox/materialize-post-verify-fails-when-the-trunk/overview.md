+++
priority = "p2"
kind = "owner-question"
summary = "Materialize post-verify fails when the trunk carries a prop equal to its CLASS DEFAULT"
+++

# Materialize post-verify fails when the trunk carries a prop equal to its CLASS DEFAULT

p2. The editor OMITS default-valued props on export, so a trunk that stores
an explicit default fails H3 post-verify. Confirmed across MULTIPLE props on the 161-actor castle
(2026-07-14): `LightPhase=0` is dropped (Light default 0) AND `LightPeriod=32` is dropped (Light
default 32) — while NON-default values of the SAME props are preserved (`LightPhase=130`,
`LightPeriod=24` survive the round-trip). So it is genuinely default-VALUE omission, not a
computed/volatile field (do NOT add these to `COMPUTED_PROPS` — that would wrongly strip a
non-default authored value too). Surfaced AFTER the qualify/LevelInfo/float32/Normal fixes landed
(those are DONE and make the castle round-trip faithful up to this point — see `decisions.md`
2026-07-14). This is the last known materialize round-trip gap. A correct general fix needs
class-default awareness — decide the approach: (a) a baked per-class default table, or (b) read a
freshly-spawned actor's defaults from the editor during materialize (it is already running), then
strip trunk props equal to the default on BOTH sides before hashing. NOT done here: it needs your
call on approach, and guessing "looks default" (e.g. any `=0`) risks erasing meaningful explicit
values. Also: the castle build helper should stop emitting default-valued Light props in the
first place. **Update 2026-07-18:** the missing class-default-VALUE capability is being built by
the `actor prop` subcommands work (spec `specs/2026-07-18-actor-prop-subcommands.md` §5 — offline
binary defaults decode, a third route beating both (a) and (b)); Andrzej decided (decisions.md
2026-07-18 10:02 §11) this verify fix stays a SEPARATE item that consumes that capability once it
lands.
