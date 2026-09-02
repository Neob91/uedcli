+++
priority = "p3"
kind = "chore"
summary = "plain `brush build` (no --prop/--texture/--mover-class) hard-requires the games config for zero validation value` — every `brush build`/`actor build` runs the a"
+++

# plain `brush build` (no --prop/--texture/--mover-class) hard-requires the games config for zero validation value` — every `brush build`/`actor build` runs the a

plain `brush build` (no --prop/--texture/--mover-class) hard-requires the games
config for zero validation value` — every `brush build`/`actor build` runs the author-time ingest
gate `_validate_ingest_actors` (`dispatch.py:2711`) before emit, which resolves the game's base
package paths (exit 2 `_NO_GAMES_CONFIG` if `~/.uedcli/config.toml` is absent) to existence-check
the class + textures. But for a plain shape the class is the hardcoded `Engine.Brush` (always
exists) and the default texture is `None` (texture loop skipped) — the gate can only ever pass, yet
it still blocks the stateless generator on config. Consider skipping the gate (or the config
requirement) when there is nothing substrate-specific to validate: fixed class, no `--texture`, no
`--prop`, no `--mover-class`. Surfaced 2026-07-21 while exercising the preview verbs.
