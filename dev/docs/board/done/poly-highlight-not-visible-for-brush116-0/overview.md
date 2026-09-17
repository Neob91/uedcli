+++
priority = "p1"
kind = "debug"
summary = "selecting Brush116:0 or Brush111:0 shows selected in the inspector but the poly draws no visible highlight"
+++

# poly highlight not visible for Brush116:0 / Brush111:0

Root-caused (NOT live-screenshot-confirmed — no browser tooling in this environment): both polys are
real, non-degenerate, correctly-attributed geometry viewed near head-on, where the highlight overlay's
`polygonOffsetFactor` term (slope-scaled) contributes ~0, leaving only `polygonOffsetUnits` to win the
depth-test tie against the coincident base mesh. Fixed by raising only `polygonOffsetUnits`'s
magnitude (`SelectionHighlight.tsx`); `polygonOffsetFactor` is untouched to avoid affecting steep-angle
surfaces. Please verify visually via the live `staging` preview.
