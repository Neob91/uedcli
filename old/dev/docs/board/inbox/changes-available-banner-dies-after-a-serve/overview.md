+++
priority = "p1"
kind = "debug"
summary = "The yellow 'trunk changed -- Reload to see it' banner stays hidden after a serve restart, for as many trunk changes as the session had Loads before it; owner-reported as worsening"
+++

# changes-available banner dies after a serve restart

Owner-reported (2026-10-03): "I feel like I'm not getting the yellow notification when the level
changes more and more these days."

**Root cause, reproduced.** `session_status` (`uedcli/serve/app.py:611`) answers
`ctx.generation[0] > session.last_seen_generation`, comparing two counters that do not share a
lifetime:

- `LevelContext.generation[0]` is IN-MEMORY, created as `generation=[0]` per level and bumped by
  `_on_trunk_settled`. It resets to 0 on every `serve` start.
- `SessionRecord.last_seen_generation` is PERSISTED in `sessions/<sid>/index.json` and bumped by
  every Load (`sessions.set_last_seen_generation`). It only ever climbs.

So a session reused across a restart compares a counter that restarted at 0 against a high-water
mark that did not. The banner is suppressed for exactly as many settled trunk changes as that
session had already Loaded. Sessions are deliberately persistent
(`to-spec/persistent-gui-editing-sessions`), so reuse across restarts is the designed workflow, not
an edge case — and because the mark only grows, the blackout gets LONGER the more the session is
used, which is the "more and more" the owner is seeing.

Reproduction (deterministic, no timing): create a session, let 3 changes settle + Load, three times
over; the in-memory generation and the persisted mark both reach 9 and the banner works. Restart
`serve` over the same sessions root and the same session: generation is back to 0, the mark is still
9, and `changes_available` stays `false` through the next 9 real trunk changes.

**Why the WS push doesn't save it.** `_broadcast_changes_available` fires correctly on every settle,
but the client does not take the push as the banner signal: `web/src/App.tsx:393` subscribes with
`() => refreshStatus(sessionId)`, so the push only triggers a `/status` refetch (and `/status` is
also polled every 3s, `STATUS_POLL_MS`). The banner is 100% whatever `/status` says, so a wrong
`/status` answer hides it even though the push arrived.

**Ruled out:** the watcher itself. `TrunkWatcher` was probed against the real `write_actor_tree`
path for modify-existing, ADD-a-new-actor (a brand-new `actors/<name>/` dir), modify-the-just-added
actor, remove, and add-then-immediately-modify — all six fired exactly once, on both the fast
filesystem and the `/workspace` bind mount. There is no added-actor-specific hole in the watch.

**Second, narrower gap found while tracing this** (same comparison, different cause, probably wants
the same fix): a trunk change that lands while `serve` is DOWN — or before that level's watcher is
started (`_lifespan` starts only the startup level's; `ws_endpoint` starts a lazily-created level's
on first connect) — fires no settle event, so nothing bumps `generation` and the banner never
appears for it either. Seeding the counter from the sessions' marks at startup fixes the restart
case but not this one; a content-derived signal fixes both.

Fix direction is an owner call, not yet decided — see `questions/`.
