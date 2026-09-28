# Spec — GUI: copy selected actors as T3D to clipboard

Written for a reader who has not seen the design discussion. Terms are defined before use.

## Goal and non-goals

**Goal.** In the GUI editor's Inspector panel, add a **Copy** button (icon + label) next to the
selection header — `{actor.name}` for a single selection, `{N} actors selected` for a multi-selection
— that copies the selected actors to the system clipboard as a **T3D** snippet: the plain-text actor
format `MAP EXPORT`/`EDIT COPY` produce in real UnrealEd (`dev/docs/unrealed/t3d.md`). The result is
pasteable into a real running UnrealEd 2.2 instance via `EDIT PASTE`.

The snippet:
- is wrapped `Begin Map\n…\nEnd Map\n` (`dev/docs/unrealed/t3d.md` "Block nesting" — the same wrapper
  real `EDIT COPY` uses).
- lists the selected actors in **CSG order** — the level's own actor/build order, not selection or
  click order (see "CSG order" below).
- reflects the actor's **current on-screen state**, including a staged (unsaved) `Location` if one is
  pending — not necessarily the last-saved trunk.
- includes uedcli's own folder/label carrier comments (`// uedcli-folder:` / `// uedcli-labels:`),
  matching what every other uedcli generator already emits for a single actor
  (`emit_actor_t3d`/`inject_carriers`, `uedcli/emit.py`). A real UnrealEd reads past them as
  unrecognized comments; pasting back into uedcli's own GUI or CLI recovers folder/label assignment.
- omits `bSelected=True` (real EDIT COPY's transient editor-selection flag) — meaningless outside a
  live editor session, and no existing uedcli emit path writes it.

**Non-goals.**
- No CLI verb. This is a GUI-only feature: a new session-scoped API endpoint backs the button;
  nothing is exposed for piping/scripting. *(Owner ruling, 2026-09-27, this item's speccing
  conversation.)*
- No paste-side (`EDIT PASTE`/"paste into the GUI") support. This spec is copy-out only.
- No copy of a surface-only selection (`SurfaceSelection`, GUI.md "Selection & the Inspector" —
  a selected polygon on an unselected actor). The button acts on the actor selection only; when an
  actor and surface selection coexist, the surface half is ignored for this feature.
- No change to what a "selected actor" is, or to selection state/behavior generally — this consumes
  the existing selection, it doesn't touch how it's formed.
- Byte-exact reproduction of real `EDIT COPY` output is not a goal beyond what's needed for a
  faithful paste (see "Brush= qualifier and carriers" below); no attempt to match its `LevelInfo`
  omission-on-select-all quirk or other selection-mechanics differences (`quirks.md` "EDIT COPY is
  not equivalent to MAP EXPORT/batchexport") — those are about what real UED22 selects, not about
  what this feature emits for whatever the GUI's own selection already is.

## Background — what exists, reused as-is

- **The T3D wrapper.** `emit_map(actors: list[Actor]) -> str` (`uedcli/emit.py:291`) already produces
  `Begin Map\n…\nEnd Map\n` from a list of `Actor`s — the exact format needed here, except it emits
  actors carrier-free (`emit_actor`, no folder/labels). Since this feature needs carriers included,
  it needs a small variant — wrap `emit_actor_t3d` (which already does `inject_carriers` +
  `emit_actor`) the same way `emit_map` wraps `emit_actor`, instead of reusing `emit_map` itself.
- **Brush= qualifier and carriers.** A brush actor's `Brush=Model'…'` prop is set when the trunk's
  on-disk T3D is loaded back into an `Actor` — `t3dtree.py:load_actor_body` (`uedcli/t3dtree.py:143`)
  rewrites it to `Model'MyLevel.Model_<name>'` — the exact qualifier real UnrealEd's own
  `EDIT COPY`/`EDIT PASTE` round-trips through (confirmed live, the salvaged spike below). So
  `emit_actor` already emits a paste-faithful `Brush=` line with no new logic; the actual
  after-the-`Begin Brush`-block emission (`uedcli/emit.py:246-249`, explained by the comment at
  `emit.py:213-221`) is the ordering real UnrealEd requires (`quirks.md` "Emit ordering (fixed
  bug)" — before the block or omitted, `MAP REBUILD` crashes or the brush comes in unbound).
- **Paste-drift: reproduce it, don't compensate.** Real `EDIT PASTE` drifts every pasted actor by a
  uniform `+32uu` on all three axes, confirmed live (not brush-specific — `quirks.md` "How brushes
  enter the level", "EDIT PASTE drift", now generalized past its prior brush-only wording) by a
  spike salvaged from an earlier, unmerged attempt at this feature (`gui-t3d-clipboard-copy`,
  commit `fd42b107`, superseded by the 2026-09-23 session/staging redesign before it could merge —
  see `dev/docs/spikes/2026-09-15-gui-copy-paste-ued22-parity/`, regression pinned in
  `test_engine_facts.py::test_edit_paste_drift_applies_to_every_actor_kind_not_just_brushes`). This
  feature must NOT pre-shift by `-32uu` the way `writes._shift_for_paste` does for uedcli's own
  automated brush re-add (that compensation exists only so THAT caller lands at an exact recorded
  location) — a human pasting a GUI-sourced clipboard into real UnrealEd should see the same drift
  any other `EDIT COPY`/`EDIT PASTE` round trip produces there; masking it would make this paste
  behave differently from every other paste in that editor, which would be the actual surprise.
- **CSG order.** `Level.order: list[str]` (`uedcli/model.py:139`) is already the full actor list in
  CSG/build order (`dev/docs/architecture.md` "T3D tree" — `order_value` is the LexoRank sidecar this
  list is sorted by). Sorting the selected names by their index in this list gives CSG order directly;
  no new ordering logic.
- **Staged (unsaved) `Location`.** `apply_staged_overlay(level: Level, staged: dict[str, StagedActor])
  -> Level` (`uedcli/serve/edits.py:189`) already returns a new `Level` with any staged `Location`
  overlaid on top of the trunk, without mutating or writing anything — the exact "current on-screen
  state" this feature needs, and the same function session-scoped Rebuild already uses for the same
  reason. (Today staging covers `Location` only — no other property is stageable for an ordinary
  actor — so this is also the full extent of "unsaved state" there is to reflect.)
- **Icon.** `web/src/scene/icons.tsx` is the existing pattern for this app's icons: hand-authored
  inline SVG, no icon-font/library dependency (deliberate — see that file's header comment). The new
  Copy icon follows the same `STROKE_PROPS` convention.
- **Session/error conventions.** The new route follows the existing `/api/session/{session_id}/…`
  family: `_require_session` for an unknown session id, and the shared domain-error handler
  (`_domain_error_handler`) for a clean, named 422 on a bad actor name — no bespoke error shape.
  Unlike the mutating routes (`/stage`, `/save`, `/discard`), this route is read-only and does not
  take or check a claim token, matching the other read-only routes (`/scene`, `/atlas`, `/lightmap`).
- **Name resolution.** `query.resolve_actor_names(level, names) -> list[str]` (`uedcli/query.py:352`)
  already resolves a batch of names to their canonical stored form, all-or-nothing, collecting every
  miss into one `KeyError(f"Actors not found: {', '.join(missing)}")` (not just the first) — the
  exact lookup the new route needs. That's a bare `KeyError`, though, and `error_to_status`
  (`uedcli/serve/errors.py`) has no arm for it — falls through to a generic 500, not the named 422
  this spec promises. The route needs a catch-and-wrap in the same spirit as
  `edits.stage_locations` (`uedcli/serve/edits.py:73-76`, which does this for its own single-name
  sibling `resolve_actor_name`) — but reusing the batch exception's own already-aggregated message
  (`except KeyError as exc: raise CommandError(str(exc.args[0])) from exc`), not reconstructing a
  single-name one, so every missing name is still named at once. A few new lines, not a new
  pattern.

## API surface

`POST /api/session/{session_id}/t3d`

Request body:
```json
{"actors": ["ActorName1", "ActorName2"]}
```
`actors` is the GUI's current actor selection (any order — the response re-sorts; a name repeated
in the list is not an error — it names the same one actor, so the route dedupes the resolved names
before emitting, and it appears once in the output). Matches `POST .../discard`'s existing
`{"actors": [...]}` shape (`uedcli/serve/app.py:924`) rather than inventing a new one.

**Deliberate departure from house convention, owner-confirmed:** every existing GET route leaves
level/session content unmutated (one, `get_session_route`, mints/supersedes a claim as a side
effect, but still takes no claim as input), and every existing mutating POST takes a claim token
except
`POST /api/level/{level_name}/sessions` (`create_session_route`) — which mints the session's first
claim, so there's nothing yet to check. This route is the first POST that's neither mutating nor
claim-checked at all. `GET` with a comma-separated `names` query param (what the salvaged prior
attempt used) would fit the GET-is-read-only half of that convention, but a JSON body was chosen
anyway — a query string is the worse fit for a bulk, possibly-long name list.

Response body:
```json
{"t3d": "Begin Map\n…\nEnd Map\n"}
```

Errors (existing conventions, no new shape):
- Unknown `session_id` → the existing `_require_session` 422.
- `actors` empty → 422, naming that it's empty (no fallback to "copy nothing" or a whole-level
  export — CLAUDE.md "no fallbacks, no silent half-answers").
- Any name(s) in `actors` not present in the session's current (staged-overlaid) level → 422 naming
  every missing one (CLAUDE.md "never let an exception reach the user… naming the offending value")
  — covers a race where the clipboard click lands after an actor was deleted/renamed elsewhere in
  the same session.

## Frontend behavior

- **Button placement.** A "Copy" button (icon + label) sits next to both existing selection headers
  in `Inspector.tsx`: the single-actor `<h2>{actor.name}</h2>` and the multi-actor
  `<h2>{actors.length} actors selected</h2>`. Both branches get the same button, wired to the same
  handler with the currently-selected actor names. (The salvaged branch instead wired this to a
  Cmd/Ctrl+C keyboard shortcut in `SelectionKeys.tsx`, with no visible button — this spec's ask was
  explicitly for a discoverable button, not a shortcut, so that interaction is not reused; nothing
  stops a future item from adding the shortcut as an additional trigger for the same endpoint.)
- **Click behavior.** On click: `POST` the current selection's names to `t3d`, then
  `navigator.clipboard.writeText(response.t3d)`.
- **Feedback.** A brief inline confirmation near the button (e.g. the label swaps to "Copied" for a
  couple seconds) on success. On failure — the request errors, or `navigator.clipboard.writeText`
  rejects (blocked permission, insecure context) — an inline error near the button, not a silent
  no-op; the user must be able to tell a copy didn't happen.
- **Scope.** Acts on the actor selection only (see "Non-goals" — surface-only selection is ignored).

## Testing

- Backend: a unit test per error case above (unknown session, empty `actors`, unknown actor
  name(s), including a multi-name-missing case asserting all are named at once), and a happy-path
  test asserting `Begin Map`/`End Map` wrapping, CSG-order sorting independent of request-list
  order, a repeated name deduplicated to one occurrence, staged-`Location` overlay reflected over
  trunk state, folder/label carriers present, and `bSelected` absent.
- Frontend: a test that the Copy button renders in both the single- and multi-actor branches, calls
  the endpoint with the current selection, writes the response to the clipboard (mock
  `navigator.clipboard.writeText`), and shows the success/failure feedback state.
