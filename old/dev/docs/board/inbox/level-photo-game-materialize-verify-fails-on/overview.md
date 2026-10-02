+++
priority = "p2"
kind = "finding"
summary = "level photo --game materialize-verify fails on multiple dev/games showcase trunks"
+++

# level photo --game materialize-verify fails on multiple dev/games showcase trunks

Found while capturing fresh `level photo` screenshots for the `unify-ue1-package-read-primitives`
item's closing deliverable. `level photo --game --tree level/<showcase>` (project `dev/games`)
fails at its internal materialize-and-verify step on every showcase trunk tried, each with a
DIFFERENT mismatch — not one trunk's content bug, more likely a systemic issue in the verify
comparison itself:

- `showcase_unatcohq`: actor `BioelectricCell3` — built omits `bOwned` (class default `False`),
  intended `bOwned=True`.
- `showcase_wanchai_market`: actor `CageLight0` — built omits `LightType` (class default `1`),
  intended `LightType=LT_None`.
- `showcase_brooklynbridge`: `Brush2` geometry at line 239 — built `Item=inner`, intended
  `Item=Inner` (case only).

Not investigated further — out of scope for the package-read item. `level photo --native` on the
same trunks (e.g. `showcase_unatcohq`) works fine, so this is scoped to the `--game` backend's
materialize-verify path specifically. `--native` render of `showcase_unatcohq`: 40.3s cold /
32.3s with the on-disk package cache warm (orbit shot, 1280x960).
