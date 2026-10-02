+++
priority = "p3"
kind = "implement"
summary = "Picker delete can show open tab superseded instead of closed"
+++

# picker delete can show open tab superseded instead of closed

Found in the final whole-branch review of the session-management-UI plan (session that landed
`SessionPicker`, path-based session URLs, and the deleted-vs-superseded distinction across the
backend/frontend).

`SessionPicker`'s delete flow does `GET /api/session/{id}` (mints a fresh claim, superseding
whatever window holds it) THEN `DELETE /api/session/{id}` -- the owner-approved acquire-then-
mutate step. If the session's own open tab is mid-poll on `/ws` during that window, it sees the
claim check fail (session still exists) before the DELETE lands, and gets `{"type":
"superseded"}` + close code 4003 -- the takeover banner, not "this session was closed." Measured
window: `_WS_CLAIM_POLL_INTERVAL_S = 0.1`, against a GET-then-DELETE round trip plus the delete's
own `rmtree` -- a real, single-digit-to-roughly-20% chance per delete, not theoretical.

Self-corrects: the takeover banner's own Reload button calls `fetchSession`, which 404s once the
delete lands, and `resolvedIdsRef` already knows this id was good -- so the tab reaches `closed`
after one extra click.

Not fixed in that session: narrowing it means reordering the picker's delete (e.g. DELETE first,
only falling back to the acquire-then-retry dance on a 409) -- a different design from the one
already approved, not a bug fix, so it needs the owner's yes before changing.
