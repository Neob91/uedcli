+++
priority = "p2"
kind = "debug"
summary = "At NYC_Bar N=4 the only parity_gate residual is the Pinball actor body: UED22 emits a Base object property (8 tagged props) that native omits (7). Native instead carries a Region/Location/Rotation set the editor's build has resolved differently. Blocks NYC_Bar N=4 byte parity; unrelated to the world-model soup iLink fix (that residual is now gone on all three levels)."
+++

# NYC_Bar N=4: Pinball actor omits the editor-set `Base` property

After the `Model.Polys` soup-iLink fix (all three ladder levels pass N=1..4 on the world model),
NYC_Bar N=4 still fails `parity_gate` with ONE residual: `BODY pinball pinball0`.

Pinball is NYC_Bar's 4th actor (N=1..3 pass), so N=4 is the first N it enters.

## Symptom (gate canon diff, native vs ued)

- ued has **8** tagged props, native **7**. ued carries a `Base` object property native lacks.
- The lists then shift: `Region` (PointRegion), `Location` (Vector), `Rotation` (Rotator) appear on
  both but at different positions because native is missing `Base`.

```
LEN [props]: native=7 ued=8
[4] native='Region' ued='Base'      # ued inserts Base here
[5] native='Location' ued='Region'
[6] native='Rotation' ued='Location'
```

## Likely cause

`Base` is the actor an object rests on / is attached to, resolved by the editor during
`MAP REBUILD` (SetBase / FindBase physics settling), not authored in the trunk. Native's actor
serialization does not compute it. This is a real editor build step, NOT a per-save-random field, so
it is not covered by the parity exclusion set.

## Scope

Separate subsystem from the world CSG soup iLink work. Needs its own investigation: when UED22 sets
`Base` on a resting actor at rebuild, and whether native should replicate it or whether it is a
candidate exclusion (would need an opus review + owner yes per the parity bar).

Reproduce: `actor_parity.py --dx 02_NYC_Bar.dx native 4` + `ref 4`, then `parity_gate.py` on the two
`_scratch/actor-parity/02_nyc_bar/*_N4.dx`.
