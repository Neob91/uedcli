+++
priority = "p3"
kind = "debug"
summary = "A degenerate-but-positive dimension exits 2 without naming the flag or the value"
+++

# A degenerate-but-positive dimension exits 2 without naming the flag or the value

`brush build extrude --depth 1e-9 --point 0,0 --point 96,0 --point 96,32` and
`brush build cube --width 256 --breadth 64 --height 0.0001` both print `invalid brush geometry:
builder: face has < 3 distinct vertices` — true, but it names neither the offending flag nor
what the user typed, so there is nothing to act on. The positive-dimension guard
(`dispatch._POSITIVE_BUILD_DIMS`) passes them because they ARE > 0; the face only collapses
later, when `_dedup_ring` welds vertices that land within `WELD` of each other. Fix at the
shared guard (a minimum representable extent, named per flag), not per verb — it affects every
shape. **Re-filed 2026-07-26:** this was the second half of the coordinate `[debug]` item, and
it was deleted along with the half that WAS fixed (the `decimal.InvalidOperation` traceback,
now `model.CoordinateError`, guarded in `emit`). Caught by the round-2 build review; the deletion was the error the
board exists to prevent, so it is logged here rather than only corrected in place.
