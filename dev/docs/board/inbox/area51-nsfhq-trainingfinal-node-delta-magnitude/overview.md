+++
priority = "p2"
kind = "debug"
summary = "Area51/NSFHQ/TrainingFinal node-delta magnitude grew under the 2026-09-03 normal/table fixes (Area51 +85->-321, NSFHQ -92->-356, TrainingFinal -59->+158) — error-cancellation exposure; no formerly-exact level regressed. Re-localize each with the Vandenberg per-brush Pass-1 trace method."
+++

# Area51/NSFHQ/TrainingFinal node-delta magnitude grew under the 2026-09-03 fixes

The Vandenberg round's two fixes (`b2199cd` float32-π GMath table, `a7be107` uniform
`SNS(X·CalcNormal(local))` normal rule) are live-evidence-confirmed editor semantics, and the
17-level cached-corpus A/B (`dev/docs/spikes/2026-09-03-vandenberg-first-divergent-brush/logs/
corpus-{before,after}.txt`) shows no node/surf/leaf-exact level losing exactness, with big wins
(OceanLab +390→+1, Vandenberg +659→+397, Club/Chateau stay 0). But three already-non-exact levels'
node deltas grew in magnitude: Area51 `+85/+0/+51`→`-321/+0/-120`, NSFHQ `-92/+1/-26`→
`-356/-2/-59`, TrainingFinal `-59/+0/-11`→`+158/+0/-17` — the same error-cancellation-exposure
precedent as Vandenberg's own `-6`→`+659` history (their old nearer counts rested on wrong inputs
cancelling downstream). Per the standing rule these are NOT re-fudged; each needs its own
localization. The Vandenberg round's method (per-brush Pass-1 gdb count trace + plane bit-diff +
stage boundaries — its spike's harness is generic enough to retarget) localized that level's
residual entirely to the world `bspRepartition`; these three likely share the class.

Reviewer also found (not node/surf/leaf, so outside this item's title but same round): the normal
rule flips `vectors`-exactness on two levels not otherwise mentioned in the spike. `09_nyc_shipfan`
goes vectors 0→+1, offset by a `points` gain (overall score holds at 4/6). `04_nyc_underground`
goes vectors 0→+1 with no offsetting gain — overall geometry score regresses 4/6→3/6, a real if
small parity regression from this round that the "no exact level loses exactness" framing didn't
cover (it only tracks node/surf/leaf). Needs its own look: which vector(s) on which brush/poly, and
whether it's the same CalcNormal rule or a downstream consumer of it.
