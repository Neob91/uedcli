# The mover keyframe workflow

Build a mover (a brush actor that animates between keyframes — see [`mover`](../reference/mover.md)
for the full `mover key` reference) and author its stops: build the base pose, raise the keyframe
count, then pose each key. This is the mover-keyframes workflow — build once, then edit keys by
index.

```bash
# 1. build the base mover (no CsgOper — a mover is out of world CSG) and add it
uedcli brush build cube --width 128 --breadth 16 --height 256 \
    --mover-class DeusEx.ElevatorMover --at 512,0,0 | uedcli actor add -

# 2. raise the waypoint count, then author each key's pose
uedcli mover key count  ElevatorMover0                      # print the current NumKeys
uedcli mover key count  ElevatorMover0 4                    # a 4-stop elevator (2..8)
uedcli mover key move   ElevatorMover0 1 --from-base --to 0,0,256   # key 1: 256uu above base
uedcli mover key move   ElevatorMover0 2 --from-world --to 512,0,512  # key 2: an absolute world pose
uedcli mover key rotate ElevatorMover0 3 --from-base --to 0,16384,0  # key 3: yaw 90° off base

# 3. inspect / nudge / remove keys
uedcli mover key list   ElevatorMover0 [--json]             # world pose + offset per key
uedcli mover key move   ElevatorMover0 1 --by 0,0,-16       # nudge the current offset (no frame)
uedcli mover key rotate ElevatorMover0 3 --by 0,8192,0
uedcli mover key remove ElevatorMover0 1                    # delete + compact indices (NumKeys--)
```

See also, for the full craft recipe: [mover-door.md](../leveldesign/general/recipes/mover-door.md),
[elevator.md](../leveldesign/deusex/recipes/elevator.md),
[lift.md](../leveldesign/general/recipes/lift.md),
[deusex-door.md](../leveldesign/deusex/recipes/deusex-door.md).

Reference: [`mover`](../reference/mover.md), [`brush build`](../reference/brush/build.md),
[`actor add`](../reference/actor/add.md).
