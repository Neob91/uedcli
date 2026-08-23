+++
priority = "p2"
kind = "debug"
summary = "materialize MAP SAVE exceeds its 600s bound on a retail-size map"
+++

# materialize MAP SAVE exceeds its 600s bound on a retail-size map

`level import`ing `06_HongKong_WanChai_Market.dx` gives a trunk of 2288 actors (1331 brush, 957
point). `level preview --game` on that trunk fails in its materialize step:

```
materialize for preview failed: materialize failed (nothing written): MAP SAVE never produced a
finished file at /work/<uuid>.dx: no file appeared (after 601s, bound 600s). The editor accepted the
command but did not complete the save — check the editor log; it most likely wedged.
```

Preceded by repeated `XGetWindowProperty[_NET_ACTIVE_WINDOW] failed (code=1)` on stderr.

Not diagnosed — three candidates, undistinguished:

- the editor genuinely wedged;
- 600s is simply short for full CSG + save on a map this size;
- something specific to this imported trunk.

The cheap control is to import a small map (`02_NYC_Bar.dx`) and materialize it: success there
points at the bound, not the verb. Nothing here shows materialize failing on ordinary levels.

The `--game` preview itself is fine on the same map via `--map` (which skips materialize) — that
path rendered lit frames from `@PlayerStart1`.

Found 2026-08-23. Unrelated to it, on that host the docker daemon refused to bind-mount any path
under `/home/agent` (`mkdir /home/agent: permission denied`), which breaks the default
`~/.uedcli/cache/stubs` mount until `$UEDCLI_HOME` is pointed somewhere mountable — environmental,
noted only so the next reader does not mistake it for this bug.
