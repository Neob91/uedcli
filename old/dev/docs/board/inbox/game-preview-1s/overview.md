+++
priority = "p3"
kind = "implement"
summary = "`--game` preview ≤1s (from ~2.2s warm)"
+++

# `--game` preview ≤1s (from ~2.2s warm)

Andrzej wants a same-map 1-shot warm
preview in ≤1s; the one-exec drive got it to ~2.2s but the dev CLI can't go sub-1s. Levers:
(1) the eventual **Nuitka release binary** removes ~0.56s Python interpreter+import startup;
(2) **fold the reuse `docker inspect` INTO the `exec`** (batch self-checks a baked fingerprint env
vs a passed arg; boot on failure) → −~0.3s; (3) **tune the settle** (`UED_SETTLE_S`, now 0.2s) — live
spike the minimum before frames go stale (biggest lever for BATCHES: 0.2s×N). Even fully optimized
the dev CLI is ~1.5-1.8s; sub-1s needs the release binary. Deferred by Andrzej ("ship ~2.2s").
