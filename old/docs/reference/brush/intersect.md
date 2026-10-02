# brush intersect

intersect / deintersect

Two **generators** that take their shape from a piped brush set instead of parameters: they read a
T3D brush set on **stdin** (`-`) and write **one** brush (or Mover) actor T3D to stdout. Model-side
and instant — no editor, no container. (They need the game's `.u` packages: a Mover in the piped set
is refused, a class-hierarchy question — see [Projects](../../README.md#projects-uedclitoml).)

```
brush intersect   - [<brush build output flags>] [--origin …] [--pivot …]
brush deintersect - [<brush build output flags>] [--origin …] [--pivot …]
```

They differ only in the background the set is merged against:

| verb | background | the set's role | result | needs |
|---------------|--------------|---------------------------------------------|-------------------------------------------|-------------------|
| `intersect`   | **empty**    | additives make solid, subtractives carve it  | the resulting **solid**, welded into one brush | ≥1 additive brush |
| `deintersect` | **solid**    | subtractives carve **voids** out of solid    | the **void** as a solid — the "negative"/plug  | ≥1 subtractive brush |

So `intersect` welds a cluster: an additive block with a subtractive notch becomes one brush shaped
like block-minus-notch. `deintersect` gives the solid that exactly fills what the set carves — the
door **plug** that fits a subtracted doorway, which is why it pairs with `--mover-class`.

```bash
uedcli actor find --folder castle.door | uedcli actor show - | uedcli brush intersect - | uedcli actor add -
uedcli stash show arch                 | uedcli brush deintersect -                     > plug.t3d
uedcli prefab show archway             | uedcli brush intersect -                       | uedcli actor add -
```

Every tier feeds them through its own `show` verb — which is why there are no `stash`/`prefab`
intersect verbs.

## Input rules

- **Stdin order IS the CSG order**, never re-sorted. A mixed add/subtract set is order-dependent
  (the last operation on a region wins): `add block, subtract notch` carves the block, the reverse
  order subtracts into empty space and leaves the block whole. You control order through the pipe.
- **Empty stdin is a clean no-op** (exit 0), like every generator.
- **Non-brush actors and Movers are refused** (exit 2, naming them) rather than skipped — a merge
  quietly missing a piece reads as a complete answer. Narrow the pipe (`actor find --kind brush …`).
- **Scaled, mirrored, and sheared source brushes build** — the transform is baked into the CSG
  input. Only a **non-invertible (degenerate) scale** (a zero or sub-epsilon axis) is refused, exit 2
  naming the brush.

## Output flags

They accept the same output-shaping flags as `brush build` — `--csg`, `--solidity`, `--texture`,
`--mover-class`, `--prop`, `--rotate`, `--base-name`, `--folder`, `--label` — with **two
verb-specific defaults**:

- **`--at` defaults to *keep the carved position*** (not the origin): omitted, the result stays
  where the set carved it.
- **`--solidity` defaults to the *faithful per-face rule***: a result face **keeps the solidity of
  the additive it came from**, and a face from a subtractive is forced solid. A **semisolid**
  additive yields semisolid faces — which **still block** (a semisolid face has the same collision as
  solid; only *nonsolid* is walk-through), so a semisolid-paned door is fine. The gotcha is a
  **nonsolid** additive: its faces come out walk-through — pass **`--solidity solid`** to scrub the
  per-face bits to plain solid. **`--solidity` is INVALID with `--mover-class`** (every value,
  `solid` included): a mover always keeps the source per-face solidity, so there is nothing to override.

## Placement — `--origin` and `--pivot`

A brush's world geometry is `world = Location + R·(vertex − PrePivot)`, so it is moved by `Location`
and rotates about `PrePivot`. The raw CSG output has `Location=(0,0,0)` and world-space vertices,
which would make a mover rotate about the *world origin*. So the result is **re-centred**:

- **`--origin center|min|max|X,Y,Z|keep`** — where the result's local origin sits. Default
  `center`. `keep` emits the raw faithful form (`Location=0`, world vertices) for diffing against
  an editor export; it rejects `--at` and `--pivot`.
- **`--pivot center|min|max|X,Y,Z`** — the world point the result rotates about, written as
  `PrePivot`. Defaults to the `--origin` anchor.
- **`--at X,Y,Z`** places the result so its **pivot** lands there.

World position is preserved by construction in every combination.

## What it refuses

The merge is faithful or it fails — it never returns a partial weld:

- a **non-brush actor or a Mover** in the piped set (exit 2, naming it) — narrow the pipe with
  `actor find --kind brush`;
- a **non-invertible (degenerate) source brush** — a zero or sub-epsilon scale axis (exit 2, naming it);
- a set with **no additive** (`intersect`) or **no subtractive** (`deintersect`), pointing you at
  the other verb;
- a **name list** on stdin instead of a T3D snippet (the two stdin conventions are easy to mix up).

Empty stdin is the one silent case: a clean no-op, exit 0, like every generator.

## Disjoint results

A set can merge into several disconnected solids (two far-apart clusters). They stay **one actor**
(as in UnrealEd) and the verb says so on stderr with the component count. There is no `--split`: run
the verb per subset for independently movable pieces — the input is a set, so that is already a
natural pipe.

See also: [the door mover flow](../../usage/door-mover-flow.md), [`stash`](../stash.md), [`prefab`](../prefab.md).
