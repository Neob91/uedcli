# Session Management UI — Design

**Status:** approved by owner, ready for planning.

## Goal

`uedcli serve`'s persistent-GUI-editing-sessions feature (shipped) has no frontend way to manage
sessions beyond switching between ones already open. This adds: a landing screen for creating and
picking sessions, a delete affordance with confirmation, path-based session URLs
(`/session/<sid>/` instead of `?session=<id>`), and session renaming.

## Current state (context, not part of this design)

- `SessionContext.tsx` reads/writes `?session=<id>` via `URLSearchParams`/`history.replaceState`. A
  bare URL (no `?session=`) auto-creates a session on the project's default level.
- `SessionDropdown.tsx` (toolbar) lists open sessions and navigates to one on click — no
  delete/rename.
- Backend already has full session CRUD: `POST /api/level/{level}/sessions`, `GET /api/sessions`,
  `GET /api/session/{id}`, `DELETE /api/session/{id}` (409 + `?force=true` override if
  `staged.json` is non-empty). Nothing in the frontend calls `DELETE`.
- `SessionRecord` (`uedcli/serve/sessions.py`): `id`, `level`, `created_at`, `last_active_at`,
  `last_seen_generation`. No name/label field.
- The SPA is served via `StaticFiles(directory=frontend_dist, html=True)` mounted at `/`. Verified
  empirically (Starlette `TestClient`, this session): this resolves `/` to `index.html` but returns a
  plain 404 for any other unmatched path — it does **not** fall back to `index.html` for an arbitrary
  client-side route.

## Decisions from brainstorming

1. The picker screen **replaces** auto-create-on-bare-URL entirely. A bare `/` always shows the
   picker; nothing is created without an explicit click.
2. Routing stays dependency-free — no router library. Two routes (`/`, `/session/<sid>/`) don't
   justify one, and it breaks this codebase's plain-hook convention.
3. A named session's name **replaces** the level as its primary label everywhere a session is
   listed (picker, toolbar), with the level shown as secondary detail. Falls back to the level name
   when unnamed, same as today.
4. Rename is inline: click the name to edit it in place; a ✓/✗ button pair plus Enter/Esc confirms
   or cancels. Available in the picker list and in a new persistent toolbar label (see "Toolbar
   session label" below) — **not** in the quick-switch dropdown itself.
5. Every place a session is shown by name (picker rows, the toolbar label, the dropdown) shows
   name-or-level as the visible text and the raw session id in a `title` attribute (hover tooltip)
   — consistent everywhere, not just the dropdown this was first asked about.
6. A new persistent toolbar label, next to `SessionDropdown`, always shows the current session's
   name-or-level and is itself the rename trigger (click it to edit inline). It also carries a
   "back to picker" link so leaving a session doesn't require the browser back button.
7. Delete always shows a confirmation dialog — never skipped, even for a session with no unsaved
   edits — but its copy differs depending on whether the session currently has staged edits.
8. The toolbar `SessionDropdown` is unchanged: quick-switch (list + navigate) only. No delete/rename
   powers added there; the picker screen is the one place for full session management.

## Architecture

### Routing

`App.tsx` currently derives its top-level view from `SessionContext`'s `view` state
(`editing | notfound | closed | superseded`). This adds a route dimension on top: which SCREEN is
shown is now also a function of `window.location.pathname`, checked before `SessionContext` even
resolves a session:

- `pathname === '/'` → render `SessionPicker` (new component). `SessionContext` does nothing on
  this route — no auto-create, no fetch.
- `pathname` matches `/session/{id}(/)?` → extract `id`, hand it to `SessionContext` (replacing
  today's `readSessionIdFromUrl`'s `URLSearchParams` read), render the existing editor tree keyed
  off `SessionContext`'s resolved `view` exactly as today.
- Anything else → treated as unmatched; redirect to `/`. In practice this branch is unreachable in
  a real deployment: since there's no generic backend catch-all (below), any path other than `/` or
  `/session/{id}` 404s at the SERVER before the SPA's JS ever loads, so this route's own client-side
  code never runs to see it. Kept as a cheap defensive no-op in case that assumption ever changes
  (a future added route, a proxy rewrite), not because it's expected to fire.

Navigating (creating a session, picking one, switching via the dropdown, closing back to the
picker) calls `history.pushState` (not today's `replaceState` — the picker and the editor are
genuinely different screens; back/forward should move between them) and updates local state to
re-render.

**Old `?session=<id>` bookmarks break, deliberately, with no migration shim.** Once this ships,
`readSessionIdFromUrl`'s `URLSearchParams` read is gone — a bookmarked `?session=<id>` URL from
before this change lands on `/`, the query string is simply ignored, and the picker shows with
nothing pre-selected. No redirect from the old shape to the new one is planned: this codebase's own
no-back-compat-cruft convention (nothing is unreleased software's problem to migrate) applies here
the same as anywhere else. Stated plainly so it isn't mistaken for an oversight later.

A tiny new module, `web/src/session/route.ts`, owns exactly this: parsing `pathname` into
`{ screen: 'picker' } | { screen: 'session', id: string }`, and a `navigate(path)` helper wrapping
`pushState` + a listener hook for `popstate`.

**`useSession` redesigned, not just re-plumbed** (spec review caught the original "otherwise
unchanged" claim as a real contradiction with decision 1 — the auto-create branch below can't
coexist with "nothing is created without an explicit click," and leaving it as unreachable dead code
violates this codebase's no-dead-code convention). `SessionContext.tsx`'s hook now takes the
resolved id as an explicit argument, `useSession(sessionId: string)` — settling the "argument, or
reads it via this new module" fork the first draft left open: an argument is more testable (no
hidden `window.location` read inside the hook) and `App.tsx` already has to parse the route to
decide which screen to render, so it already has the id in hand to pass down. Concretely:

- The whole "no session id in the URL at all → auto-create on the default level" branch inside
  today's `reload()` is DELETED, not kept — `useSession` is only ever mounted from the
  `/session/{id}` route branch, which always has a concrete id. The picker owns creation itself
  (`POST /api/level/{level}/sessions` → `navigate()`), never through this hook.
- `createSession` is dropped from `UseSessionResult`'s surface entirely, for the same reason — no
  caller needs it anymore.
- `reload()` becomes "re-fetch `sessionId` (the argument), mint a fresh claim, activate" — no more
  `readSessionIdFromUrl()` call. Its existing behavior as "what the superseded-takeover Reload
  button calls" is unchanged in effect, just re-scoped to the passed-in id instead of a URL read.
- `activate()` drops its `writeSessionIdToUrl(rec.id)` call outright — there's no URL left for this
  hook to own. Writing the path is `route.ts`'s `navigate()`'s job alone, called from `App.tsx`
  (creating a session, picking one in the picker, switching via the dropdown) — never from inside
  `SessionContext.tsx`.
- One consequence worth naming: since `reload`'s own dependency array includes `sessionId`, the
  existing mount-only `useEffect(() => reload(), [reload])` now ALSO re-fires whenever the argument
  itself changes — so switching sessions via the dropdown no longer needs an explicit `reload()`
  call from `App.tsx` after navigating; changing the id `App.tsx` passes into `useSession` is
  sufficient on its own.

`SessionDropdown.tsx`'s pre-load fallback option (`<option value={currentSessionId}>
{currentSessionId}</option>`, shown before the session list has fetched) is left showing the raw
id — there's no `name` available for it at that point anyway, so it isn't part of decision 5's
"consistent everywhere" (which is about sessions the list actually returned).

### Backend: one new route for the new path shape

`create_app`'s route registration gains, before the `StaticFiles` mount:

```python
@app.get("/session/{session_id}")
def spa_session_route(session_id: str) -> FileResponse:
    return FileResponse(frontend_dist / "index.html")
```

**Settled, not deferred** (spec review flagged the earlier "settled during planning" phrasing as
exactly the kind of API-shape detail this project's own speccing rule says to settle now, not push
downstream — and this one was already checked, so there's nothing left to defer): FastAPI's default
`redirect_slashes=True` behavior already 307-redirects `/session/<id>/` to this route's own
`/session/{session_id}` for a single dynamic-segment path like this one — confirmed earlier in this
session with a throwaway `TestClient` probe. No second explicit route is needed for the
trailing-slash form. This is the ONLY new backend route for serving the frontend; deliberately not
a generic catch-all for arbitrary future paths (YAGNI — nothing else needs one yet).

Two things caught in review, worth stating plainly rather than leaving implicit:

- **Gated on `frontend_dist is not None`**, same as the existing `StaticFiles` mount. A dev setup
  with no built frontend has neither route today; this one follows the identical rule rather than
  existing unconditionally.
- **No server-side validation of `session_id`.** This route serves `index.html` unconditionally for
  any id-shaped path, real or not — exactly like the SPA's own client routing already treats an
  unknown `?session=` id today. A bogus id resolves entirely client-side, to `SessionContext`'s
  existing `notfound` view, once the JS loads and calls `GET /api/session/{id}` itself.

### The picker screen

New `web/src/session/SessionPicker.tsx`. Two pieces of state it owns: the level list
(`fetchLevels()`, already exists) and the session list (`GET /api/sessions`, already exists).

- **Create**: a `<select>` of levels + a "Create session" button. On click,
  `POST /api/level/{level}/sessions` → navigate to `/session/{new id}/`.
- **List**: one row per session — name-or-level as the primary label (inline-renamable, see
  below), level as secondary text when named, `last_active_at`, a Delete button. Sorted by
  `last_active_at` descending (most recently used first). Clicking a row (not the name or the
  Delete button) navigates to `/session/{id}/`.

### Rename

**Schema** (`uedcli/serve/sessions.py`): `SessionRecord` gains `name: str | None = None`. Read via
the same `data.get("name")` backward-compatible pattern `last_seen_generation` already uses for a
session record written before this field existed.

**A real hazard, caught in spec review — not just the read side.** `atomic_write_json` is a full
overwrite, not a merge, and `touch_session`/`set_last_seen_generation` (`sessions.py`) each already
re-read the record via `get_session` first, then write back an EXPLICIT field dict that would omit
`name` unless updated: `atomic_write_json(..., {"id": rec.id, "level": rec.level, "created_at":
rec.created_at, "last_active_at": ..., "last_seen_generation": ...})`. `touch_session` runs on
essentially every session-scoped request (`_require_session`'s own chokepoint, throttled to once
per 30s) and `set_last_seen_generation` runs on every Load — so without a fix, a session's name
would get silently erased back to `None` the next time either of these fires after a rename. Both
functions add `"name": rec.name` to the dict they already build (they already have `rec` in scope
from their own `get_session` call, so this is a one-line addition each, not a new read).

**Backend**: `POST /api/session/{id}/rename`, body `{"name": string}`, claim-token gated (`X-Claim-
Token` header, same convention as every other mutating session route — `409` on a stale token). An
empty or whitespace-only name persists as `None` (clears back to showing the level). Response:
`{"id", "level", "created_at", "last_active_at", "name"}` — no `claim_token` field; renaming isn't
a "resolve" operation and mints nothing.

**Unknown-session status code, settled (spec review flagged this as a real fork, not a "check and
match" detail)**: this route resolves its session id via `_require_session` — the SAME chokepoint
`session_load`/`session_stage`/`session_discard`/`session_save`/`session_rebuild` already use — so
an unknown id raises `CommandError` → **422**, not the bare 404 `get_session_route`/
`delete_session_route` use. Rename belongs with the first group: it's mutating and claim-gated the
same way, unlike `GET`/`DELETE`, which don't share that shape (`GET` takes no claim token at all;
`DELETE`'s own 404 check runs before any claim check, not through `_require_session`). Its own
claim-check-fails branch reuses the SAME `_claim_conflict_response` helper the "Distinguishing
'deleted' from 'superseded'" section below adds — rename races with delete the identical way the
other five mutating routes do, so it gets the same fix, not a sixth bespoke one. The write itself
goes through a new `sessions.set_name(sessions_root, session_id, name)` — the same
read-then-full-rewrite shape `touch_session`/`set_last_seen_generation` already use (and, per the
hazard noted above, one that already carries every OTHER field forward correctly by construction,
since it's the one function actually setting `name`).

**Claim-token gap, caught in self-review**: rename and delete both require a valid claim token, but
the PICKER lists sessions this browser tab may never have opened — there's no token in hand for
most rows there. Fix, scoped to the picker only: for both rename and delete FROM THE PICKER, the
frontend first calls `GET /api/session/{id}` (mints a fresh claim token, same as opening it
normally would) immediately before the mutating call, and uses that token. This is a real,
deliberate side effect worth stating plainly: renaming or deleting a session from the picker
supersedes whatever window currently holds its claim — the same "whichever window last resolved it
wins" rule already governs every other claim mint, and it's the right behavior here too (you're
about to rename/delete it out from under that window regardless).

**Not the toolbar label's rename, though (spec review caught this as a real self-supersede risk)**:
`SessionLabel`'s own rename (below) is for the session THIS window already has open — it already
holds a valid claim token in `SessionContext`'s `claimToken` state, already pushed into `api.ts`'s
module-level `currentClaimToken` (`App.tsx`'s existing `setClaimToken(claimToken)` effect, the same
mechanism every `postStage`/`postSave`/`postLoad`/`postRebuild` call already relies on). Its rename
call must use that already-held token directly, via the SAME `withClaimToken` header helper those
calls use — never the picker's acquire-then-mutate `GET` step. Re-minting here would supersede the
window's OWN claim against itself, and its very next Stage/Save/Load/Rebuild would then 409 as
"superseded" against a takeover that never really happened.

**Frontend**: a small shared component, `web/src/session/InlineRename.tsx` — click-to-edit text
with ✓/✗ buttons and Enter/Esc handling, taking the current display value and an `onRename(name)`
callback. Used by both `SessionPicker`'s rows and the new toolbar session label below (see
"Toolbar session label") — not inside `SessionDropdown`, which stays list-only per the decision
above.

**Data plumbing, easy to miss**: `name` has to actually reach the frontend to be shown anywhere.
`GET /api/sessions` and `GET /api/session/{id}` (both already exist) both gain `name` in their
response body, same field as the new rename response — `POST /api/level/{level}/sessions` does
NOT (a just-created session is always nameless; nothing consumes it from that response). `api.ts`
has THREE separate session-shaped interfaces, not one, so this is precise about which change: only
`SessionSummary` (`fetchSessions`) and `SessionDetail` (`fetchSession`) gain `name: string | null`,
matching the two backend responses that actually carry it; `SessionRecord` (`createSession`) is
untouched. Every caller that reads one of the first two (`SessionDropdown`, `SessionPicker`, the
toolbar label) gets `name` for free once its type does.

### Display: name-or-level everywhere, id on hover

Decision 5 above, made concrete: anywhere a session is shown by name — `SessionPicker` rows, the
new toolbar label, `SessionDropdown`'s own option text — the visible text is name-or-level (the
existing fallback rule) and the element carries `title={id}` so the raw session id is one hover
away. `SessionDropdown.tsx` currently renders `<option value={s.id}>{s.id}</option>` (the raw id as
the visible text); this changes it to name-or-level with `title={s.id}` on the `<option>`, and
nothing else about the dropdown (still list + navigate only, per decision 8).

### Toolbar session label

New `web/src/session/SessionLabel.tsx`, rendered in `App.tsx`'s toolbar next to
`SessionDropdown` (decision 6). Always visible once a session is loaded: shows name-or-level
(`title` = the raw id, per the rule above), and clicking it swaps in `InlineRename` for that
session — same component and same ✓/✗/Enter/Esc mechanics `SessionPicker`'s rows use, wired to the
same `POST /api/session/{id}/rename` call.

It also carries a small "back to picker" link/button — plain navigation to `/` via `route.ts`'s
`navigate()`, no confirmation (leaving a session doesn't discard anything; staged edits and the
build pin are exactly as durable as switching sessions via the dropdown already is today).

### Delete

Clicking Delete: fetch `GET /api/session/{id}/staged` (already exists) to determine whether the
session has unsaved edits, then show a confirmation dialog whose text depends on that result:

- Empty: "Delete this session?"
- Non-empty: "This session has unsaved edits. Delete anyway?"

On confirm: mint a claim token for this session first (`GET /api/session/{id}`, see the claim-token
gap noted under Rename above — the same acquire-then-mutate step), then `DELETE /api/session/{id}`
with that token, `?force=true` appended only when the staged check found edits (a plain `DELETE` on
a session that does have edits would 409 pointlessly, since we already know). On success, remove
the row from the picker's own list state (no need to re-fetch the whole list).

### Distinguishing "deleted" from "superseded" (owner decision, 2026-09-23)

The claim-token acquire-then-mutate step (above) means deleting a session from the picker, while
another window has that same session open, supersedes that window's claim exactly like any other
claim mint does. Renaming a session genuinely IS a takeover ("superseded" is accurate: the session
still exists, another window's claim now holds it), but deleting it is not — the session is gone,
and "another window took over" is the wrong story to tell that window. Owner ruling: show "deleted"
for real, not folded into "superseded."

**The backend already has both strings; it just doesn't use the right one when the claim check
itself is what fails.** Read directly from the current code (`uedcli/serve/app.py`):

- `session_load`/`session_stage`/`session_discard`/`session_save` (lines 721/765/799/822) and
  `session_rebuild`'s post-solve check (lines 567-568) each open with
  `if not _claims.check(session_id, token): return 409 {"error": "session superseded"}` —
  unconditionally, with **no existence check on this branch at all**. The existing
  `sessions.get_session(...) is None` re-check (source of the ALREADY-correct `"session deleted"`
  string these same routes emit) only runs in the claim-check-**success** branch, guarding a
  *different* race (a delete landing between the claim check and the write). So the one case that
  actually needs the distinction — the claim check *failing* — never looks at whether the session
  still exists, and always says "superseded."
- Why this matters in practice: `ClaimRegistry.forget()` (called by `delete_session_route`, after
  the on-disk delete) removes the session's token entry entirely, and `ClaimRegistry.check()`
  auto-accepts any token for an entry it doesn't have — so a stale request arriving *after*
  `forget()` has run sails past the claim check and correctly reaches the existing "deleted" check.
  The misleading window is narrower than "any time it's deleted": specifically, a stale request
  landing between the disk delete and `forget()` (or, for the picker's own delete flow, at any
  point after its `GET /api/session/{id}` acquire step superseded the claim but before the `DELETE`
  itself completes) still fails the claim check first and never gets to look.
- **Fix**: a new helper, `_claim_conflict_response(session_id: str, *, suffix: str = "") ->
  JSONResponse` — checks `sessions.get_session(_sessions_root, session_id) is None` and returns 409
  `{"error": f"session deleted{suffix}"}` if so, else 409 `{"error": f"session superseded{suffix}"}`.
  Replaces the bare 409 return at all five claim-check-fails sites above; `session_rebuild` passes
  `suffix=" mid-solve"` to keep its existing wording (`"session deleted mid-solve"`/`"session
  superseded mid-solve"`), the other four pass nothing. No other route needs this: the WS pre-accept
  rejection (`ws_endpoint`, right after confirming the session exists moments earlier in the same
  request) and `delete_session_route`'s own claim check (same thing, `rec` was just fetched a few
  lines above) are both already unambiguous — existence was just confirmed synchronously, so a
  mismatch there is never actually a deletion.
- **`ws_endpoint`'s mid-poll loop** already checks existence *before* the claim check (an earlier
  fix round's own "Critical finding") and already tracks two close codes, 4004 (deleted) vs 4003
  (claimed) — but deliberately sends the client the identical `{"type": "superseded"}` message
  either way, on the stated reasoning that "the practical action is identical either way." That
  reasoning is what this decision overrides: send `{"type": "closed"}` on the 4004 (deleted) branch,
  keep `{"type": "superseded"}` on the 4003 (claimed) branch.

**Frontend, precisely** (spec review caught the naive version of this: deriving `reason` from the
thrown Error's own `.message` doesn't work, since `request()` prefixes the URL onto it —
`` `${url}: ${message}` `` — so `.message.startsWith('session deleted')` is always false). Fix at
`api.ts`'s `request()` (current shape: `let message = res.statusText`, then inside the `try`,
`if (body.error) message = body.error`): compute `reason` from `body.error` directly, in that same
`if` branch, BEFORE it's folded into `message`/the Error — `reason = body.error.startsWith('session
deleted') ? 'deleted' : body.error.startsWith('session superseded') ? 'superseded' : undefined` —
and attach it to the thrown Error the same way `status` already is (`err.reason = reason`).
`isSupersededError` narrows to exclude `reason === 'deleted'` (so it stays permissively `true` for
any other 409, same fallback as today, including one with no recognized reason at all); a new
`isClosedError` is `true` exactly when `status === 409 && reason === 'deleted'`.

The WS side gets a matching `ClosedMessage` (`{type: 'closed'}`) alongside the existing
`SupersededMessage`; `openChangesAvailableSocket` dispatches it to a new `onClosed` callback
parameter. `subscribeChangesAvailable` (`reload.ts`) gains a 5th parameter, `onClosed: () => void`,
and its internal `connect()` needs a NEW wrapper mirroring the existing one — today only
`onSuperseded` has a `stopped = true; onSuperseded()` closure inside `connect()`'s
`openChangesAvailableSocket(...)` call; `onClosed` needs the identical treatment
(`stopped = true; onClosed()`), not just a passed-through callback. Only the `close`-event
listener's OWN body (the reconnect-vs-give-up logic) is unaffected, since both wrappers already set
`stopped = true` before that listener ever runs — the plan should scope the "no change needed" claim
to exactly that listener body, not the whole file.

`SessionContext.tsx` gains `markClosed()` — setting `view: 'closed'`, the SAME view value `reload()`
already reaches by a different path (re-resolving a session id this hook once knew was good and
finding it 404 now). Every current `onSuperseded` wiring gains a sibling `onClosed`, routed to
`markClosed`, with each call site keeping its own existing calling convention (not a uniform
`?.()`) — the two shapes already differ today and this doesn't change that:

- `App.tsx`'s WS subscription call (`subscribeChangesAvailable(..., markSuperseded)` →
  `..., markSuperseded, markClosed`) and its shared `runBuildAction` (Load/Rebuild's 409 catch,
  which calls the hook functions directly, no `?.`): `if (isClosedError(e)) markClosed(); else if
  (isSupersededError(e)) markSuperseded()`.
- `SaveBar.tsx`'s `SaveBarProps` gains a new optional prop, `onClosed?: () => void`, alongside the
  existing `onSuperseded?: () => void` — its three internal 409 catches (Save, whole-level Discard,
  per-actor conflict-discard) each become `if (isClosedError(e)) onClosed?.(); else if
  (isSupersededError(e)) onSuperseded?.()`, matching this component's own existing optional-prop
  pattern. `App.tsx`'s `<SaveBar onSuperseded={markSuperseded} .../>` gains `onClosed={markClosed}`.

`postStage`'s own error handling is untouched — it never routes through
`isSupersededError`/`onSuperseded` at all today (a plain error banner regardless of status), so it's
not part of this distinction either way.

## Testing

- Backend: the new `/session/{id}` route (serves `index.html`, verified via a real file on disk in
  the test's own `tmp_path`); the rename endpoint (success, empty-name-clears, claim-token 409,
  unknown-session **422** via `_require_session` — not 404); a rename surviving a subsequent
  `touch_session`/`set_last_seen_generation` call (the name-erasure hazard above) — real regression
  coverage, not just a unit test of the write function in isolation; the deleted-vs-superseded 409
  distinction on all six claim-gated mutating routes (the five pre-existing ones plus rename)
  (`_claim_conflict_response` returns "session deleted" once the session no longer exists, "session
  superseded" when it still does but the token doesn't match — both need a real created-then-deleted
  session and a real stale-but-different token, not just a missing one) and the WS mid-poll loop's
  `{"type":"closed"}` vs `{"type":"superseded"}` split.
- Frontend: `SessionPicker` (create flow, list rendering, delete's two confirm-copy branches,
  row-click navigation vs. name-click/delete-click not navigating), `InlineRename` (edit/confirm/
  cancel via both mouse and keyboard), `SessionLabel` (renders name-or-level, `title` = id, click
  swaps in `InlineRename`, the back-to-picker link navigates to `/`, and its rename does NOT
  re-mint a claim token — a real test double on `setClaimToken`/the module-level token, confirming
  the request carries the session's own already-held token, not a freshly-acquired one),
  `SessionDropdown` (option
  swaps in `InlineRename`, the back-to-picker link navigates to `/`), `SessionDropdown` (option
  text is name-or-level, `title` = id — updated from the existing raw-id-text test), `route.ts`
  (path parsing, `pushState`/`popstate`), `SessionContext.tsx`'s updated tests for taking a
  session id from the new route module instead of `URLSearchParams` (plus new `markClosed` cases),
  `api.ts`'s `isClosedError`/`isSupersededError` (both reason strings, and the no-reason fallback),
  and each of `App.tsx`'s `runBuildAction`/`SaveBar.tsx`'s three catches routing a "deleted" 409 to
  `onClosed` and a "superseded" 409 to `onSuperseded`, never both.

## Explicitly out of scope

- No router library.
- No changes to `SessionDropdown`'s own capabilities (still list + navigate only).
- No generic SPA catch-all route — only the one new path shape this design actually adds.
- No bulk session operations (delete-all, etc.) — one at a time, per the ask.
