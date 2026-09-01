+++
priority = "p2"
kind = "debug"
summary = "RESOLVED: --game frames looked stale — really a swallowed config error, not a cache"
+++

# --game frames looked stale — root cause was a swallowed config error (RESOLVED)

Symptom: `level preview --game` (via the demo's `demo/build.py`) returned byte-identical PNGs across
runs despite lighting + geometry changes.

**Root cause (confirmed): not a cache.** The shared home config
`_scratch/uedcli-home/config.toml` carried an invalid key `ignore_props` under `[games.deusex]`, so
**every** `uedcli` call exited 2. `demo/build.py`'s `sh()` ignored exit codes, so the trunk never
built (only `LevelInfo`), the `--game` render never ran, and the old committed baked PNGs were copied
back each run. `level preview --game --rebuild` mints a fresh map correctly — there is no stale
preview cache.

**Fixed:**
- Removed the `ignore_props` line from the shared config (live fix; the key is not a real setting).
- Hardened `demo/build.py` `sh()` to run under bash `pipefail` and RAISE on any non-zero exit, so a
  broken config fails the demo build loudly instead of silently shipping empty frames.

Residual value → see [[level-preview-game-output-should-be-uniquely]]: a content-hashed `--game`
output name would have made this obvious immediately (the filename wouldn't change when it should).
That enhancement stays open; this staleness item is resolved.
