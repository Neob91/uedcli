+++
priority = "p2"
kind = "implement"
summary = "Align `class classify set` to REFUSE an existing shard (+`--force`), matching the all-kinds ruling; it currently union-merges."
+++

# Align `class classify set` to refuse an existing shard

Owner ruled 2026-08-02: `classify set` over an existing shard **refuses (exit 2), `--force` to replace**
— one rule for every kind (texture/class/sound/music), per `direction/safety.md` (never silently
overwrite authored work).

The shipped **class arm** (`class classify set`) instead **union-merges** tags into an existing shard
(`uedcli/class_catalog.py` / `uedcli/cli/commands/classes.py`). Change it to refuse + `--force` so it
matches the ruling and the texture/audio arms.

Small change: the classify-set write path + `--force` flag + tests. Update `docs/usage.md` if it
documents the merge behaviour. This is a behavioural change to already-merged code, so it needs its own
build + regression (a `set` over an existing shard exits 2; `--force` replaces).
