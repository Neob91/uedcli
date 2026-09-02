# Unify `vertex`/`clip` multi-actor on the NAME-LIST set, not on extending `BRUSH:SELECTOR`?

## Context

The board overview proposes making `BRUSH:SELECTOR` (`Wall1:3,5 Wall2:all`) the shared pattern for
`vertex` and `clip` too. But `BRUSH:SELECTOR`'s `:SELECTOR` is a poly-**index** list: `poly` has
indices, while `vertex` selects corners by coordinate and `clip` cuts a whole brush by a plane —
neither has an index list to put after the colon. The pattern that DOES fit both, and already exists,
is the name-list stdin set (`find | verb -`) that `brush scale`/`apply-transform` use — "a verb over a
set takes the set."

- Option A (recommended): `clip` and `vertex move` take a NAME SET (`names… | -`); `BRUSH:SELECTOR`
  stays poly-only; the "shared helper" is the existing `targets.resolve_target_names` (no new parser).
- Option B: force `BRUSH:SELECTOR` onto `vertex`/`clip` as the board wrote it — which means inventing a
  colon-selector meaning for verbs that have no sub-face indices.

Recommendation: A. This contradicts the overview's literal wording, so it needs your call before
building.

## Answer

<!-- Empty = open. -->
