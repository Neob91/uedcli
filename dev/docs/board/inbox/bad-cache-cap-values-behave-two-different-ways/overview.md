+++
priority = "p3"
kind = "chore"
summary = "Bad cache-cap values behave two different ways.` `uedcli cache gc --max-bytes -1` exits 2 naming the flag (new, 2026-07-25), while `UEDCLI_SCHEMA_CACHE_MAX_BYTE"
+++

# Bad cache-cap values behave two different ways.` `uedcli cache gc --max-bytes -1` exits 2 naming the flag (new, 2026-07-25), while `UEDCLI_SCHEMA_CACHE_MAX_BYTE

Bad cache-cap values behave two different ways.` `uedcli cache gc --max-bytes -1`
exits 2 naming the flag (new, 2026-07-25), while `UEDCLI_SCHEMA_CACHE_MAX_BYTES=-1` is silently
ignored and falls back to the built-in default (`schema_cache._env_int`, deliberate: "a bad
override must never raise"). Defensible as-is — a typo'd env var must not break every command,
whereas a typo'd flag is a direct instruction — but if the divergence bothers you, the env path
could at least warn once on stderr. Surfaced by the #9 build-review gate (2026-07-25).
