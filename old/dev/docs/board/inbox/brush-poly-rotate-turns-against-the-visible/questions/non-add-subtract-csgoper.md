# `brush poly rotate` on a brush whose `CsgOper` is neither `CSG_Add` nor `CSG_Subtract`: keep the refusal, or default to unflipped?

## Context

The 2026-07-27 ruling defines the turn against the **visible surface normal** — flip `n̂` on a
subtract — and that is built and pinned. But a brush with no defined inside and outside gives "the
visible surface normal" no direction to name, so no sign can be derived from the ruling's principle.

The set this covers is **every value that is not `CSG_Add` or `CSG_Subtract`** — `CSG_Intersect`,
`CSG_Deintersect`, `CSG_Active`, and anything unrecognised or malformed. Stated exactly because the
code refuses all of them and an earlier version of this item named only the first two; ruling on the
narrower set would leave the wider one undecided.

Currently `rotate` exits 2 naming the value — a deliberate fail-closed interim, not a reading of the
ruling: guessing a sign would be silent and look like the author's mistake, and relaxing an error to
a default later is harmless where the reverse is not. The case is close to unreachable —
`CSG_Intersect`/`CSG_Deintersect` are live-editor verbs that don't appear in a trunk, and no fixture
carries anything but `CSG_Add`/`CSG_Subtract` — so the alternative (treat them all as additive, i.e.
unflipped) costs nothing either. **Keep the refusal, or default them to unflipped?**

An ABSENT `CsgOper` is not part of this question: it already reads as `CSG_Add` in every reader, and
an unflipped non-subtractive brush follows from the ruling as written. (`normalize.py` identifies
UnrealEd's transient BUILDER brush by exactly that absence — its op is `CSG_Active`, written by
omitting the line — so the absent case is the one that actually occurs.)

Separately, not covered by the ruling: a negative `MainScale` component mirrors the brush and flips
every face's handedness, so the turn still inverts there. Documented in `docs/usage.md` rather than
corrected.

## Answer

<!-- Empty = open. Write the decision here. -->
