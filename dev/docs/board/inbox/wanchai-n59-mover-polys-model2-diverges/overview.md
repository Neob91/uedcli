+++
priority = "p2"
kind = "debug"
summary = "WanChai N=59 (new ceiling after the N=58 permeating-light fix): world Model2's Polys array diverges on a brush that isn't the LevelInfo/permeating-light mechanism -- unrelated new bail, not investigated yet."
+++

# WanChai N=59 — world Model2 Polys diverge

Found while re-verifying the fix for `wanchai-n58-leaf-51-permeating-light-over-included`
(now closed — see that item and `NATIVE-MATERIALIZE.md`'s "portal-graph frozen before
`bspOptGeom`" fix). WanChai now runs byte-exact N=1..58 and bails at N=59 on a DIFFERENT,
unrelated mechanism.

## The divergence

    ladder_run.py --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 59 --to 59
    -> FAIL -- BODY polys polys@model model2: canonical bodies differ
       native=('polys', None, [('b', b'\x10\x00\x00\x00\x10\x00\x00\x00\x04'),
               ('PB', (-489.3725891113281, -512.0, 3200.0)), ...
       ued=   ('polys', None, [('b', b'\x01\x00\x00\x00\x01\x00\x00\x00\x04'),
               ('PB', (-128.0, -253.99998474121094, 704.0)), ...

The `Polys` (FPoly soup) array attached to world `Model2` differs — a different `PolyFlags`/base
point on at least the first entry shown. Not yet root-caused: could be the newly-added N=59 actor's
own brush geometry, its poly-flags derivation, or an unrelated ordering shift exposed by it landing
at this position. NOT investigated — found only by re-verification, no time spent diagnosing.

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
        --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 59 --to 59

## Next step

Root-cause with `structure_diff.py`/`model_dump.py` on the N=59 native vs ref pair, per the usual
lockstep method (`NATIVE-MATERIALIZE.md`). Check what actor N=59 is (trunk order) and whether it's a
mover/brush whose own poly-flags or base-point derivation differs from the editor's.
