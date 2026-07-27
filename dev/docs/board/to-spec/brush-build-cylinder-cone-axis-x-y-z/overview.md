+++
priority = "p2"
kind = "implement"
summary = "`brush build cylinder/cone --axis x|y|z` — build a prism oriented along a chosen axis, no `--rotate`"
+++

# `brush build cylinder/cone --axis x|y|z` — build a prism oriented along a chosen axis, no `--rotate`

`cylinder`/`cone` always build along **+Z**; to lay a horizontal pipe, beam,
or duct run the author must `--rotate` the brush — which (a) forces reasoning about which of
pitch/yaw/roll maps to which world axis (undocumented; see the orientation doc gap). An
`--axis x|y|z` builds the cross-section normal along that axis directly, emitting **no `Rotation`
field** — so the common horizontal-pipe case needs no `--rotate` and the obvious first attempt just
works.
**NAMING IS ALREADY SETTLED — adopt it, don't re-litigate:** board item `brush-build-cylinder-cone-sides-has-no-upper`
§2.2 (`decisions.md` 2026-07-25 00:14 UTC D3) defines `--axis x|y|z` on the new `extrude`/`revolve`
generators as "the axis the profile plane is normal to", with the `(u,v)` → world mapping fixed by
right-handed cyclic order (`z`→X,Y; `x`→Y,Z; `y`→Z,X). Use that same flag name, semantics and table
here so the family is consistent. Note also that the same spec (D9) replaces `--angle-offset DEG`
with the boolean `--align-to-side`, so this item's composition question is now "how does `--axis`
compose with `--align-to-side`" (answer should be: trivially — the bool is defined relative to the
shape's own axis). Spec: which shapes take it
(`cylinder`/`cone`; `cube` is symmetric so N/A; `sheet`?), how it composes with `--align-to-side` and
`--at` (still center-anchored?), and whether to generalize to a free direction vector later. **Why it
matters:** in a cold-agent build session (2026-07-24) the agent built a horizontal pipe via
`--rotate 0,0,16384` and had to guess which rotation axis lays a +Z prism onto Y — `--axis` removes
that guesswork (build it oriented, no `--rotate`). Related: the "semisolid = freedom / build detail
from primitives" doc gap. (The post-verify abort that originally co-motivated this is now FIXED by
the `Rotation` zero-omit canonicalization, `decisions.md` 2026-07-24 21:40 UTC — so `--axis` now
stands on the axis-mapping ergonomics alone.) (Surfaced by the cold-agent build session, 2026-07-24.)
