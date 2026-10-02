# The door mover flow

The door-mover flow turns an existing door-shaped hole in a wall into a working mover: find the
door actors, deintersect the plug that fills the doorway as a fresh mover, then keyframe it to
swing open.

```bash
uedcli actor find --folder castle.door | uedcli actor show - \
  | uedcli brush deintersect - --mover-class Engine.Mover \
        --pivot min --at 4096,2048,128 \
  | uedcli actor add -
uedcli mover key count Mover0 2
uedcli mover key rotate Mover0 1 --by 0,16384,0        # swings about the hinge, not the centre
```

See also, for the full craft recipe: [mover-door.md](../leveldesign/general/recipes/mover-door.md),
[elevator.md](../leveldesign/deusex/recipes/elevator.md),
[lift.md](../leveldesign/general/recipes/lift.md),
[deusex-door.md](../leveldesign/deusex/recipes/deusex-door.md).

Reference: [`actor find`](../reference/actor/find.md), [`actor show`](../reference/actor/show.md),
[`brush intersect`/`brush deintersect`](../reference/brush/intersect.md),
[`actor add`](../reference/actor/add.md), [`mover`](../reference/mover.md).
