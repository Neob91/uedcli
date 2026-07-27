+++
priority = "p2"
kind = "owner-question"
summary = "What should `brush poly rotate` do on a brush whose `CsgOper` is neither `CSG_Add` nor `CSG_Subtract`?"
+++

# What should `brush poly rotate` do on a brush whose `CsgOper` is neither `CSG_Add` nor `CSG_Subtract`?

Your 2026-07-27 ruling defines the turn against the **visible
surface normal** — flip `n̂` on a subtract — and that is built and pinned. But a brush with no
defined inside and outside gives "the visible surface normal" no direction to name, so no sign can
be derived from the ruling's principle.

**The set this covers is EVERY value that is not `CSG_Add` or `CSG_Subtract`** — `CSG_Intersect`,
`CSG_Deintersect`, `CSG_Active`, and anything unrecognised or malformed. Stating it exactly because
the code refuses all of them and an earlier version of this item named only the first two: ruling
on the narrower set would leave the wider one undecided.

**Currently `rotate` exits 2 naming the value.** That is a deliberate fail-closed interim, not a
reading of your ruling: guessing a sign would be silent and would look like the author's own
mistake, and relaxing an error to a default later is harmless where the reverse is not. The case is
close to unreachable — `CSG_Intersect`/`CSG_Deintersect` are live-editor verbs that do not appear
in a trunk (`preview_native` says the same and skips them), and no fixture in the repo carries
anything but `CSG_Add`/`CSG_Subtract` — so the alternative (treat them all as additive, i.e.
unflipped, like an absent `CsgOper`) costs nothing either. **Keep the refusal, or default them to
unflipped?**

(An ABSENT `CsgOper` is *not* part of this question: it already reads as `CSG_Add` in every reader
in the codebase, and an unflipped non-subtractive brush follows from your ruling as written. Note
that `normalize.py` identifies UnrealEd's transient BUILDER brush by exactly that absence — its op
is `CSG_Active`, which the editor writes by omitting the line — so the absent case is the one that
actually occurs, and an explicit `CsgOper=CSG_Active` would be unusual.)

Separately and NOT covered by the ruling: a negative `MainScale` component mirrors the brush and
flips the handedness of every face on it, so the turn still inverts there. Documented in
`docs/usage.md` rather than corrected.
