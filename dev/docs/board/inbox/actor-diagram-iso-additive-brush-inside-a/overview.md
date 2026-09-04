+++
priority = "p?"
kind = "bug"
summary = "actor diagram iso: additive brush inside a subtract draws on top of the subtract"
+++

# actor diagram iso: additive brush inside a subtract draws on top of the subtract

In `actor diagram --view iso` (wire), an additive brush that sits wholly inside a
subtracted volume is painted on top of the subtract's near edges instead of being
depth-ordered as interior — the pillar reads as being in front of the room's near
wall, not inside it.

Repro (no game assets needed):

```
P="--project dev/games"
uedcli $P brush build cube --width 768 --breadth 512 --height 288 --csg subtract --at 0,0,144 --base-name Room
uedcli $P brush build cylinder --height 288 --radius 32 --sides 8 --at -256,-160,144 --base-name Pillar
# …concatenate several pillars + a staircase into scene.t3d, then:
uedcli $P actor diagram --from-t3d scene.t3d --layout single --view iso --annotate none --out /tmp/iso.png
```

Owner-observed 2026-09-04 while picking a README hero image. Not yet triaged for
priority or whether the fix is a paint-order/depth sort in the iso wire renderer.
