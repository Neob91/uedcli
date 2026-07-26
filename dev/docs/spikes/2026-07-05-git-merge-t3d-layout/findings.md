# Spike: `git merge` on the git-native per-actor-dir trunk layout

**Date:** 2026-07-05. **Gates:** the git-native model (decisions.md 2026-07-05; spec
`specs/2026-07-05-uedcli-git-native-model-design.md` §10, build step 0). **Harness:** `run_spike.sh`
(pure git, throwaway repo — reproducible) + `encoding_test.py`. **Verdict: GO.** The layout merges as
designed; one accepted-friction constraint surfaced (intra-file adjacent-line edits); encoding
settled.

Layout under test: `uedcli/maps/<lvl>/actors/<name>/{actor.t3d, order_value}`.

## Results (all 8 scenarios PASS)

| # | Scenario | Result | Expected? |
|---|---|---|---|
| 1 | Concurrent disjoint adds (two new random-named dirs) | **CLEAN** | ✅ yes |
| 2 | Concurrent SAME-gap adds (equal `order_value`, different names) | **CLEAN** | ✅ yes |
| 2 | `(order_value, name)` sort is total + deterministic | **0 dup keys** | ✅ yes |
| 3 | Reorder the SAME actor (both rewrite one `order_value`) | **CONFLICT** | ✅ correct |
| 4 | Reorder DIFFERENT actors | **CLEAN** | ✅ yes |
| 5 | modify/delete (A deletes actor dir, B edits its `actor.t3d`) | **CONFLICT** | ✅ correct |
| 6a | `LevelInfo0` **adjacent**-line edits (Title line2 + Author line3) | **CONFLICT** | ⚠️ see below |
| 6b | `LevelInfo0` **same**-line edits | **CONFLICT** | ✅ correct |
| 6c | `LevelInfo0` **non-adjacent**-line edits (Title line2 + Song line4) | **CLEAN** | ✅ yes |
| 7a | Shared `name` file, both branches change it | **CONFLICT** | ⚠️ see below |

## What this confirms (the core model holds)

- **Coordination-free adds work.** Disjoint and same-gap concurrent adds merge with zero conflict
  because each actor is its own directory with a random-suffix name — no shared file, no add/add
  name collision.
- **`(order_value, name)` is a total, deterministic order.** With two actors at the *same*
  `order_value` (`p`), the merged set sorts to a single well-defined order (X_aaa111 before Y_bbb222,
  by name) with **0 duplicate `(order_value, name)` keys** — no ties, no nondeterminism. This is the
  central ordering claim, validated.
- **Real conflicts are exactly the right ones:** reordering the same actor, and modify-vs-delete of
  the same actor, conflict (a human must decide) — and nothing else does. Reordering *different*
  actors is clean.

## New constraint surfaced: intra-file adjacent-line edits conflict (accepted)

**6a vs 6c is the finding.** Git auto-merges concurrent edits to a *single* `actor.t3d` only when the
changed lines are **non-adjacent** (≥1 unchanged context line between them). Two branches editing
*adjacent* property lines of the same actor conflict — even though the properties are semantically
independent — because git has no unchanged line between the hunks to anchor the merge.

- **Who it hits:** the `LevelInfo0` singleton (two people tweaking nearby level settings — title vs
  author) and any actor two branches both edit near the same spot.
- **Severity: low, accepted.** It is a normal, correctly-flagged, human-resolved git conflict — the
  per-actor-file split already confines the blast radius to *co-edited actors*, never the whole level.
- **Optional mitigation (plan-time):** the T3D emitter can space property groups with blank/context
  lines so independent edits are less often adjacent. Not required.

## `name` file → derive from the dir

7a confirms a single shared `name` file is a merge point (concurrent changes conflict — the exact
failure mode that killed the shared `order` file). **Recommendation (confirms spec §13 lean): derive
the level name from the `maps/<lvl>/` directory name — no `name` file, nothing to conflict.**

## Encoding settled: variable-length (LexoRank), not float

`encoding_test.py`:
- **float64 midpoint EXHAUSTS after 52 subdivisions of one gap** — you cannot insert between two
  neighbours past that. Unusable for concurrent "insert between" under branching.
- **A variable-length key never exhausts** (5000 subdivisions, exact; the denominator just grows).
- **Verdict:** use a variable-length encoding. **Recommend LexoRank-style lexicographic strings** —
  git-diff-friendly, rebalance-free, human-legible. (Confirms the spec §13 lean; the exact string
  codec is a plan-time impl detail.)

## Bearing on the build

GO on the git-native model. Fold into the plan: (1) `order_value` = LexoRank strings; (2) derive the
level name from the dir (drop the `name` file); (3) document adjacent-line intra-actor edits as an
accepted user-resolved conflict, with optional emitter spacing as a mitigation. The editor-path risks
(brush-model-ref re-injection, H3 derived-order reproduction) are NOT covered here — they move to
slice-3 acceptance per the spec's Review-resolutions section.
