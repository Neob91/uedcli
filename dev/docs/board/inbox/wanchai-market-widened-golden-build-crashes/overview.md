+++
priority = "p2"
kind = "bug"
summary = "Building 06_HongKong_WanChai_Market's golden with the widened (movers-excluded) actor set crashes the editor reproducibly at the first EDIT PASTE -- narrow-set build still works fine"
depends-on = ["texture-ref-i-actor-divergence-traced-to-golden"]
+++

# Wanchai Market widened golden build crashes editor at first EDIT PASTE

Found while widening `build_ued_lit_golden.py`'s default actor set (see
`texture-ref-i-actor-divergence-traced-to-golden` round 2). `06_HongKong_WanChai_Market`'s trunk
(2288 actors) builds its NARROW golden (`{Brush,LevelInfo}∪lights`, ~928 actors) fine -- it's the
existing cached reference golden this whole effort's Wanchai measurements use. Building the WIDENED
golden (every class except `Engine.Mover`/`DeusEx.BreakableGlass`, 2261 actors) crashes:

```
error: UnrealEd has crashed — a 'Critical Error' dialog is open
uedcli.driver.DriverError: exec EDIT PASTE failed:
```

Reproduced twice, identical failure point both times (right after `MAP NEW`, at the first
`_re_add`-issued `EDIT PASTE`) -- not the usual "editor wedges silently, differently each time"
flakiness (`unrealed/quirks.md` "Stability"), a deterministic crash given this specific actor set.
DX.dx (37 actors) and UNATCO (1437 actors, including all 28 `DeusExMover`s) both built their widened
goldens successfully, including a UNATCO run with movers explicitly INCLUDED (`--keep-classes ALL`,
1437 actors) -- so it isn't simply "more actors than the narrow default" or "movers specifically".
Wanchai's widened set is the largest tried (2261 actors) and the only one with `BreakableGlass`
excluded alongside `DeusExMover`, either of which could be relevant, but neither was isolated.

Not investigated further this round (out of scope, budget; retry-once-then-file-a-finding per
`dev/docs/rules/build-run.md` already applied -- 2 attempts, same failure point). Wanchai's existing
narrow golden is untouched and still valid; only the widened rebuild is blocked.

## Repro

```
H=dev/docs/spikes/2026-08-27-native-light-apply-parity/harness
.venv/bin/python $H/build_ued_lit_golden.py --trunk <wanchai-trunk> --out /tmp/wanchai_widened.dx --overwrite
```

Trunk used this round: extracted fresh via `parity_pipeline.ensure_golden` from
`dev/games/substrate-deusex/Maps/06_HongKong_WanChai_Market.dx` (cache hash
`0ee8d2b48d3c881ad7d93bc44e7c122dc006d1115fe937b6e4700510028ef79f`), not committed (scratch).

## Next steps, not started

- Isolate whether it's actor COUNT (2261 vs UNATCO's 1437), a specific class (e.g. something in
  Wanchai not present in UNATCO/DX.dx), or `BreakableGlass` exclusion specifically, by building
  smaller intermediate `--keep-classes` subsets.
- Check whether it's a resource/timeout issue (bigger `_re_add` batch takes longer) vs a genuine GPF
  on a specific actor's T3D.
