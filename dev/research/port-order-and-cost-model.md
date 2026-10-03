# Port order and cost model for the Rust rewrite

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** How big is the port, in what order can verbs come across, and what does the spec's
named first slice (`brush build`) actually drag in?

Complements [`rust-workspace-architecture.md`](rust-workspace-architecture.md), which answers where
the *crate* boundaries fall. This note answers *sequencing and size*: what to port when, and the
measured cost of each choice. All figures below were measured in this worktree on 2026-10-03.

## Summary

- The port is **67,242 LOC of Python product code in 220 modules**, plus 73,342 LOC of tests, plus
  31,938 LOC of existing Rust in `old/uedcli-native/` and 23,954 LOC of TypeScript in `old/web/src`.
  Product Python is the only part with no Rust equivalent yet.
- The CLI surface is **154 parser nodes / 124 leaf verbs / 662 flags** over 17 families. Two
  families, `brush` (29 verbs) and `actor` (27 verbs), are 45% of the verbs and 53% of the flags.
- **`brush build`'s model layer is genuinely small and genuinely isolated** — 24 modules, 7,738 LOC,
  and it does **not** reach the renderer. The spec's choice of first slice holds up.
- But **going through the CLI path drags the renderer in**: `cli.parsers.brush` →
  `cli.parsers._arguments` → `preview`, adding 2,847 LOC of Pillow renderer to a verb that does not
  render. One import edge decides whether PR #2 is 7,738 LOC of dependency or 11,627.
- Dependency depth is **20 layers deep** but **61% of modules sit at depth ≤ 7**, and only 7,420 LOC
  is at depth 0. There is a real bottom to build from.
- **3,476 LOC in 11 modules is unreachable from `cli.main`** — candidates for "do not port", pending
  a check of whether anything else enters them.
- `uedcli.config` (641 LOC, 29 importers, depth 0) is the single highest-leverage first port: no
  internal dependencies and nearly every other module needs it.
- Test weight is wildly uneven: `uedcli.builders` is 763 LOC of product code with 34,422 LOC of
  tests naming it; `uedcli.uscript.conimport` is 703 LOC with 141. Port order should follow the
  oracle coverage, not the product LOC.

## What we have today

| Tree | Scope | Size |
|---|---|---|
| `old/uedcli/` (excl. `tests/`) | Python product code | 67,242 LOC, 220 modules |
| `old/uedcli/tests/` | Python tests | 73,342 LOC, 253 files, 4,430 test functions |
| `old/uedcli-native/` | existing Rust (CSG/BSP/light/paths/render) | 31,938 LOC |
| `old/web/src/` | TypeScript GUI frontend | 23,954 LOC |
| new root | Rust proxy skeleton | `src/main.rs` + `tests/proxy.rs` |

The suite collects far more than 4,430 cases once parametrised: a board item records
`35 failed, 13086 passed` on a 2026-09-02 full run (`board item
bin-test-red-on-master-board-schema-tests`).

## Findings

### The verb surface, measured

Built by calling `uedcli.cli.main.build_parser()` directly (stdlib-only; no venv needed) and walking
the argparse tree.

| Family | Leaf verbs | Flags | `--help` chars |
|---|---|---|---|
| `brush` | 29 | 215 | 98,772 |
| `actor` | 27 | 133 | 65,626 |
| `level` | 9 | 41 | 16,644 |
| `class` | 9 | 42 | 15,592 |
| `texture` | 9 | 47 | 12,556 |
| `stash` | 7 | 36 | 17,393 |
| `sound` | 7 | 22 | 6,063 |
| `music` | 7 | 22 | 6,134 |
| `prefab` | 5 | 27 | 15,691 |
| `mover` | 5 | 19 | 6,510 |
| `docs` | 3 | 5 | 1,762 |
| `cache` | 2 | 4 | 1,533 |
| `event` | 1 | 4 | 1,422 |
| `uscript` | 1 | 5 | 1,530 |
| `substrate` | 1 | 3 | 627 |
| `project` | 1 | 2 | 595 |
| `serve` | 1 | 3 | 389 |
| **total** | **124** | **662** | **272,448** |

Flags count every optional action per node, `-h` included (154 of the 662). Max tree depth is 4
(`uedcli brush build cube`).

Two incidental checks:

- **Every flag has `help=` text.** Zero exceptions across all 154 nodes. The house rule holds.
- The whole help tree is 272,448 chars — roughly 68k tokens if an agent were ever to read all of it.
  Root `--help` alone is 3,609 chars. Relevant to the progressive-disclosure question in
  [`agent-drivable-tool-surface.md`](agent-drivable-tool-surface.md).

### Dependency depth: there is a real bottom

Depth = the longest internal-import chain under a module (cycles cut at the revisit guard).

| Depth | Modules | LOC | Cumulative LOC |
|---|---|---|---|
| 0 | 55 | 7,420 | 7,420 |
| 1 | 24 | 4,606 | 12,026 |
| 2 | 10 | 3,268 | 15,294 |
| 3 | 12 | 4,192 | 19,486 |
| 4–7 | 31 | 10,841 | 30,327 |
| 8–11 | 33 | 13,535 | 43,862 |
| 12–15 | 41 | 19,523 | 63,385 |
| 16–20 | 14 | 3,857 | 67,242 |

55 modules import nothing internal at all. That is the natural first tranche, and it is only 11% of
the LOC — so a bottom-up port spends its first weeks on a small fraction of the mass. Depth 12–15
holds 19,523 LOC (29%) and is where the renderer, survey, GUI backend and the CLI command modules
live.

### The highest-leverage early ports

Depth-0 modules ranked by how many other modules import them:

| Module | LOC | Importers | Test LOC naming it |
|---|---|---|---|
| `uedcli.config` | 641 | 29 | 16,949 |
| `uedcli.uprops` | 107 | 27 | 19,378 |
| `uedcli.typedprops` | 511 | 12 | 2,926 |
| `uedcli.native.codec` | 128 | 10 | 1,326 |
| `uedcli.container_assets` | 119 | 9 | 1,682 |
| `uedcli.folderlib` | 126 | 8 | 253 |

`uedcli.config` is the obvious first real port: zero internal dependencies, 29 downstream modules,
and a very large body of tests already pinning its behaviour.

The hubs overall (most-imported, any depth) are `uedcli.model` (43 importers), `uedcli.cli.errors`
(38, but only 26 LOC), `uedcli.config` (29), `uedcli.rotation` (27), `uedcli.uprops` (27),
`uedcli.upackage` (24), `uedcli.emit` (23).

### What the first vertical slice actually costs

The spec names "a single brush builder" as PR #2's slice: "pure function, no editor, no git-trunk
I/O". Transitive internal-import closures:

| Slice (seed modules) | Modules | LOC |
|---|---|---|
| `builders` + `profile` | 24 | 7,738 |
| `cli.commands.brush` + `cli.parsers.brush` | 28 | 11,627 |
| `model` + `emit` + `normalize` + `typedprops` | 12 | 3,225 |
| `query` | 24 | 7,738 |
| `upackage` + `uprops` + `classindex` | 9 | 2,423 |
| `driver` (the editor driver) | 3 | 739 |
| `preview` + `preview_native` | 54 | 20,458 |
| `actor_survey` + `relation` | 58 | 25,546 |
| `serve.app` (GUI backend) | 89 | 27,100 |
| `uscript.compile` | 29 | 12,532 |
| whole CLI (`cli.main`) | 209 | 63,766 |

Two findings worth the owner's attention:

**1. The renderer leaks into the brush parser.** `builders` does not reach `preview` — but the CLI
path does, in two hops:

```
cli.parsers.brush -> cli.parsers._arguments -> preview
```

`_arguments` is the shared-argument module every parser imports, and it imports the 2,847-LOC
renderer (presumably for a shared render-flag definition or an enum of view modes). So "port
`brush build cube` end to end" is 7,738 LOC of dependency if the Rust parser defines its own flags,
and 11,627 if it mirrors the Python module structure. Worth checking before PR #2 fixes the shape by
accident. `preview`'s other importers are `cli.rendering`, `preview_native`, `preview_wire`,
`relation` and `serve.scene` — `relation` is the surprising one there.

**2. The builders reach the query layer.** `builders -> surface -> query`, and `query` is depth 12.
`surface` imports `query` for what is presumably a lookup helper. That edge is why the
builders-only closure is 24 modules rather than a handful, and why its depth is 10 rather than 2.

### Code that may not need porting at all

11 modules, 3,476 LOC, are unreachable from `cli.main` by internal imports:

| Module | LOC | Likely reason |
|---|---|---|
| `uedcli.uprops.values` | 548 | re-exported via the `uprops` facade, not imported directly |
| `uedcli.uscript.gate` | 545 | uscript surface may be partly unwired |
| `uedcli.propedit.edit` | 507 | `propedit` package not on the CLI path |
| `uedcli.native.csg_golden` | 417 | test/golden support |
| `uedcli.game.preview_batch` | 330 | zero importers anywhere |
| `uedcli.qualify` | 279 | ? |
| `uedcli.propedit.fields` | 278 | with `propedit.edit` |
| `uedcli.uscript.reference_ut99` | 201 | reference corpus support |
| `uedcli.uscript.reference_dxorig` | 190 | reference corpus support |
| `uedcli.uscript.reference` | 154 | reference corpus support |
| `uedcli.__main__` | 27 | entry point, reached from outside |

This is *static* reachability only: a module entered via `importlib`, a plugin hook, a test, or a
re-export string would not show up. `uedcli.__main__` proves the method has false positives. Treat
the list as a to-check, not a delete list. There is an existing board item
`dead-code-removal-follow-ups` in `to-spec/` that this would feed.

### Test coverage is not proportional to code

Test LOC naming each module (crude: any file mentioning the module's bare name), against product
LOC:

| Module | Product LOC | Test LOC | Ratio |
|---|---|---|---|
| `uedcli.builders` | 763 | 34,422 | 45× |
| `uedcli.cli.commands.level` | 825 | 55,090 | 67× |
| `uedcli.uscript.parser` | 1,078 | 20,990 | 19× |
| `uedcli.preview` | 2,847 | 16,641 | 5.8× |
| `uedcli.uscript.compile` | 3,299 | 3,940 | 1.2× |
| `uedcli.actor_survey` | 2,449 | 3,345 | 1.4× |
| `uedcli.uscript.conimport` | 703 | 141 | 0.2× |

The mentions heuristic overcounts common names, so read the ratios as rank, not magnitude. The rank
still carries a real signal for the differential-testing plan: the brush builders are the
best-oracled part of the tree, which is a second, independent reason the spec's first slice is the
right one. `uscript.compile` and `actor_survey` are the two largest modules with the thinnest
proportional coverage — they are where differential testing will have to generate its own inputs
rather than lift fixtures.

### Import cycles

Eight mutual (2-module) cycles exist in the product code:

```
utexture <-> utexture_decode      pkg_cache <-> upackage
model <-> transform               writes <-> rotation
transform <-> rotation            transform <-> emit
xfer <-> driver                   apply <-> native.unbuilt
```

Each is held legal at runtime only by Python's tolerance for function-local imports. Rust has no
equivalent, so each cycle is a forced crate-merge or a forced refactor.
[`rust-workspace-architecture.md`](rust-workspace-architecture.md) analyses the full
strongly-connected components, which is the right granularity; this list is the 2-cycle subset and
agrees with it.

Note `architecture.md` documents a *different* cycle — `profile.py` owning `WELD` so `builders` can
import it without a load-time cycle. That one was avoided by design; these eight were not.

## Options

A port order has to trade off three things: proving the pipeline early, porting against the best
oracle, and not stalling on the deep layers.

| Order | Pros | Cons |
|---|---|---|
| Strict bottom-up (depth 0 first) | every port has its dependencies already in Rust; no stubs | ~7,400 LOC before any verb works end to end; no user-visible progress for a long stretch |
| Vertical slices (spec's plan) | a working verb at every step; proves arg-parse → model → emit → dispatch immediately | each slice re-ports some of the bottom; needs care that slice 2 reuses slice 1's crates rather than forking them |
| Best-oracle first (`brush`, then `actor`) | maximum differential-test confidence per LOC; retires the largest families early | `brush` is 29 verbs — a long single-family stretch before the shape is tested against a different family |
| Leaf-families first (`docs`, `project`, `substrate`, `cache`, `event`) | 6 verbs, ~5,500 help chars, tiny closures; clears 5 families fast | they are the least representative verbs; proves little about the model layer |

These are not exclusive — the spec already picks vertical slices, and "best oracle first" is a way
of choosing *which* slice.

## Proposal (owner's call — not decided)

1. **Before PR #2, check the `_arguments → preview` edge.** If the Rust brush parser can define its
   flags without pulling in render options, PR #2's dependency footprint drops by 2,847 LOC and the
   renderer stays out of the first crate graph. If it cannot, that is worth knowing before the shape
   is set.
2. **Port `uedcli.config` as its own early PR**, ahead of or alongside the first builder: depth 0,
   29 importers, heavily tested, and every later slice needs it.
3. **Sequence the families by oracle strength, not size**: `brush` → `actor` → `level` → the rest,
   with the five single-verb families (`project`, `substrate`, `event`, `uscript`, `serve`) held to
   the end since four of them front subsystems that are themselves unported.
4. **Resolve the 11 unreachable modules before porting anything that touches them** — confirm each
   is dead and record it, or find the entry point. Feed the answer to board item
   `dead-code-removal-follow-ups`.
5. **Treat the eight cycles as the crate-merge list**, and decide per cycle whether to merge or
   break it *before* the crate it belongs to is created, not after.

## Open questions / what to verify next

- Why does `cli.parsers._arguments` import `preview`? One grep settles whether it is a shared enum
  (cheap to break) or real shared logic.
- Why does `surface` import `query`? That edge sets the builders' depth at 10 instead of ~2.
- Are the 11 statically-unreachable modules actually dead? `uedcli.game.preview_batch` has zero
  importers anywhere, which is the strongest case.
- What is the real collected test count today, and how many of those 13,086 are parametrised
  variants of the same assertion? That number, not the 4,430 functions, is the fixture-extraction
  workload.
- Does any verb family have *no* offline test coverage (i.e. tests that need Docker/Wine/game
  assets only)? Those cannot be differential-tested on a clean host.

## Sources

All figures measured in this worktree on 2026-10-03:

- LOC and module counts: `find`/`wc -l` over `old/uedcli`, `old/uedcli-native`, `old/web/src`.
- Import graph, depths, cycles, closures: `ast`-based static analysis of `old/uedcli/**/*.py`
  (product code only, `tests/` excluded), resolving absolute and relative `import`/`from` forms
  plus the `from pkg import submodule` case.
- Verb/flag/help figures: `uedcli.cli.main.build_parser()` walked directly, `format_help()` per node.
  Independently corroborated against the git-tracked fixture
  `old/uedcli/tests/fixtures/parser_baseline/help.json` (same 272,448 total).
- Test function count: `grep -c "^def test_"` over `old/uedcli/tests/*.py`.
- The 13,086-passed figure: board item `bin-test-red-on-master-board-schema-tests`, a 2026-09-02
  full-suite run.

Unverified: the "test LOC naming a module" heuristic is a name-mention count, not real coverage. A
`cargo-llvm-cov`-style per-module coverage figure would replace it; `coverage.py` over the existing
suite would give the honest number.
