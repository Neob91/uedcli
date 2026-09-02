# Plan — actor-name composition pipe (`-` on name-takers + `actor add` name output)

Spec: [`spec.md`](spec.md)
(§8 review-gate resolutions are authoritative). Ephemeral; fold learnings into the durable docs
once landed.

## Goal
Close the compose pipe at both ends:
- **Producer** — `actor add` prints the allocated Names to **stdout** (one/line, allocation order),
  after `src.save()`; the `added N actor(s)` summary moves to **stderr**.
- **Consumers** — `actor delete`, `actor rotate`, `actor prop set|unset|get`, `actor show` accept
  the single token `-` in their name position → read a newline-separated name list from stdin.
  (`actor move` deliberately does NOT; `actor folder set` not built yet — skipped.)

## Steps + touchpoints

1. **`dispatch.py` — shared helper `_resolve_target_names(tokens) -> list[str]`.**
   - `-` present with other names → `_SelectionExit` (exit 2).
   - sole `-` → read stdin, splitlines, strip, drop blanks; empty → `[]`.
   - else → the CLI names verbatim. Canonical resolution + dedup are the caller's (§8).

2. **`dispatch.py` — `actor add` output split** (~2213): print `touched` Names to stdout AFTER
   `src.save()`, then `added N actor(s)` to stderr.

3. **`dispatch.py` — `actor delete`** (~2164): route `args.names` through the helper; empty → no-op
   exit 0; resolve (plural msg) + `dict.fromkeys` dedup (fixes latent double-`pop` KeyError).

4. **`dispatch.py` — `actor rotate`** (~2262): route `args.names` through the helper; empty → no-op
   exit 0 (already dedups).

5. **`dispatch.py` — `actor prop set|unset|get`** (~2217): `piped = args.name == "-"`. Route
   `[args.name]` through the helper; empty → no-op exit 0. Non-piped keeps singular resolve
   ("Actor not found:") + records `{"name": ...}`; piped uses plural resolve + records
   `{"names": ...}`. **Two-phase** set/unset: build per-actor `_class_ctx` + `plan_edit` for ALL
   actors first, then apply all + one save (bad token leaves all untouched, cross-class safe).
   `get`: build all output lines first (atomic), then print; piped → `<name>\t<key>=<value>`
   (kv shape), non-piped → today's bare/`--kv` output.

6. **`dispatch.py` — `actor show`** (~2076): intercept `args.name == "-"` BEFORE the glob path;
   read stdin list, resolve (plural) + dedup, concatenate `canonical_actor_t3d` blocks.

7. **`cli.py`** — no positional grammar change needed (`-` is a valid positional value for both the
   single-name and `nargs="+"` positionals); help strings updated to mention `-`.

8. **Tests** — `tests/test_actor_name_compose.py` for §6/§8; update `test_dispatch.py:237`
   (count moves out→err, Names on out).

## Non-goals
No model/trunk change. `actor move`, `actor find` (already a producer), folders — untouched.
