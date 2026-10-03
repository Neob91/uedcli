+++
priority = "p2"
kind = "debug"
summary = "The GUI fetches /scene and /atlas concurrently against the level-shared trunk slot, so a Load landing between them pairs one trunk's tex_index values with another trunk's atlas table"
+++

# /scene and /atlas are fetched in parallel over a mutable trunk slot

Found by code review while landing `changes-available-banner-dies-after-a-serve`. Pre-existing and
unrelated to that change, so filed rather than fixed there.

`web/src`'s `fetchSceneBundle` issues `/scene` and `/atlas` concurrently. Both read the
level-shared `ctx.trunk_ref[0]` slot, and a `POST /load` (another window's, or this window's own
Save-triggered auto-Load) can swap that slot between the two responses. `ScenePoly.tex_index`
values are indices into the atlas table published with the SAME trunk, so a mismatched pair
renders polys against the wrong texture rows — wrong textures, or an out-of-range index, until the
next refetch.

Needs a design call on the mechanism: a generation/digest token echoed by both routes so the client
can detect a torn pair and refetch, or one combined endpoint that reads the slot once. The trunk
digest `/status` already computes (`t3dtree.stamp_digest`) is a ready-made token.
