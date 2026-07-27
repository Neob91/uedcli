+++
priority = "p2"
kind = "implement"
summary = "Re-measure the SOUND corpus on the composed search path before the audio arm is specced."
+++

# Re-measure the SOUND corpus on the composed search path

Owner ruling 2026-07-26 ("spike first, then spec"). The old spec's scope rule was sized by
numbers taken over directories the tool does not load: it claimed 10,826 Sound exports with ~10,200
`DeusExConAudio*` VO; re-measured on the real configured path (119 package stems) it is **747 exports and
ZERO `DeusExConAudio*`** — those packages exist only under `System.bak/` (18) and `SystemOk/` (18), and a
whole-install walk gives 31,059, which is where 10,826 came from. The pattern also **misses the VO that is
actually there** — `LUM_ConversationsAudioMission20` (109) and `TNM` (84) — so it would have leaked the
project's own conversation audio into `sound list` while reporting "excluded: 0".

**Measure, on the composed path only:** Sound exports per package; the Outer group structure (tracked
`DeusExSounds.u` has 399 across 10 groups — `Weapons` 91, `Generic` 85, `Animal` 57, `Player` 56); how
much is genuinely conversation VO and how it is identifiable; and whether `sound list` needs any default
filter at all at that size. **Then** decide whether a per-substrate config key is warranted — do not
design the rule first. Findings fold into
`spec.md`. Two downstream claims also need re-basing on the result:
the plan's hot-author-path cost criterion, and the engine spec's ObjectProperty-validation worked example.
*(2026-07-26.)*
