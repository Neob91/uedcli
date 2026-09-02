+++
priority = "p2"
kind = "debug"
summary = "Four write paths still omit a property against a hardcoded zero/constant"
+++

# Four write paths still omit a property against a hardcoded zero/constant

The
2026-07-25 00:36 UTC contraction work established "no write path omits a property to mean zero"
(an omitted property re-imports as the CLASS DEFAULT) and fixed it in `dispatch`/`normalize`/
`transform`. These four were left, all measured harmless against the CURRENT DX class set but all
the same shape: `movers.set_key_pos`/`set_key_rot` drop an all-zero `KeyPos(i)`/`KeyRot(i)`;
`movers._set_numkeys` drops `NumKeys` when it equals a hardcoded **2**; `movers.canonicalize_mover`
deletes `Rotation` when the base pose folds to identity — **and that one runs on the map-INGEST
path, into the durable trunk**; `native/materialize.py:456-461` skips a zero `Location` (the
`Engine.Camera` bug verbatim, unwired from the CLI today). Not fixed with the rest because
rewriting mover keyframe emission churns every mover trunk on disk for a case no `Engine.Mover`
subclass currently reaches (verified: none defaults `NumKeys`/`KeyPos`/`KeyRot`, and the only
class defaulting `Rotation` is not a mover). Surfaced by both cold reviews. (2026-07-25 00:36 UTC.)
