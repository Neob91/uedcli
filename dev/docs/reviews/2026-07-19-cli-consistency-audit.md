# CLI consistency & clarity audit (2026-07-19)

**Scope:** the complete `uedcli` verb surface after build items 1–11 landed.
**Rubric:** the "Code & CLI conventions" section of `Tools/uedcli/CLAUDE.md` — the
composability philosophy (producers → stdout one-per-line; summaries/counts → stderr;
`--json` where scripted; mutators read their set from stdin via `-`; a verb over a SET
takes the set and that IS the operation, no redundant set-flags; prefer a stateless
`find`/query verb over per-command filter flags; `set|unset|get` sub-verb shape; every
flag has a real `help=`; no Python exception reaches the user; errors name the offending
value).

**This audit ships NOTHING but this report.** No code changed. Accepted findings become
new queue items later. Line numbers are `uedcli/cli.py` unless prefixed `dispatch.py`.

---

## 1. Verb inventory

Legend — **P** = producer (writes result to stdout), **M** = mutator (writes the
trunk/box), **G** = stateless generator (T3D → stdout, no level). "`-`" = accepts a
`-` stdin set. "json" = has `--json`.

| Verb | kind | `-` stdin | `--json` | notes |
|---|---|---|---|---|
| `actor find` | P | n/a (is the source) | ✓ | filter flags `--class/--group/--name/--prop/--kind/--folder/--no-folder`; names → stdout 1/line |
| `actor show <name>` | P | ✓ (name list) | ✗ | glob-capable; T3D blocks to stdout |
| `actor build <Pkg.Class>` | G | ✗ | ✗ | `--at/--base-name/--prop/--rotate`; T3D → stdout |
| `actor add <file>` | M | ✓ (**T3D snippet**) | ✗ | allocated names → stdout, count → **stderr** |
| `actor folder set --to P names…` | M | ✓ (name list) | ✗ | `set/unset/get` shape |
| `actor folder unset names…` | M | ✓ | ✗ | |
| `actor folder get names…` | P | ✓ | ✗ | prints folder or `(none)` per actor |
| `actor order names…` | M | ✓ | ✗ | `--first/--last/--before/--after`; "reordered N" → **stdout** |
| `actor delete names…` | M | ✓ | ✗ | **silent** on success |
| `actor bbox names…` | P | ✓ | ✓ | `--field`; summary → **stderr** (model pattern) |
| `actor move <name>` | M | ✗ | ✗ | **single name only**; `--to/--by`; silent |
| `actor rotate names…` | M | ✓ | ✗ | `--to/--by` + `--pivot/--pivot-actor`; "rotated N" → **stdout** |
| `actor scale names…` | M | ✓ | ✗ | `--to/--by` + pivot; "scaled N" → **stdout** |
| `actor apply-transform names…` | M | ✓ | ✗ | "baked N" → **stdout** |
| `actor prop get <name> [keys…]` | P | ✓ | ✗ (`--kv`) | effective values; piped output name-prefixed KV |
| `actor prop set <name> toks…` | M | ✓ | ✗ | |
| `actor prop unset <name> toks…` | M | ✓ | ✗ | |
| `brush build <shape>` | G | ✗ | ✗ | `_common_build_opts`: `--at/--base-name/--csg/--solidity/--group/--texture/--mover-class/--rotate`; **no `--prop`** |
| `brush clip <name>` | M | ✗ | ✗ | single name; no-op message → **stdout** |
| `brush replace <name> -` | M | ✓ (**T3D snippet**) | ✗ | single target |
| `brush vertex list <name>` | P | ✗ | ✗ | table |
| `brush vertex move <name>` | M | ✗ | ✗ | single name; `--to/--by` |
| `brush preview names…` | P | ✗ | ✗ | writes image; path → stdout |
| `brush poly list <name>` | P | ✗ | ✓ | table/JSON |
| `brush poly find <name>` | P | n/a (source) | ✓ | `BRUSH:idx` → stdout; summary → **stderr** |
| `brush poly set targets…` | M | **✗** | ✗ | `BRUSH:SELECTOR` positionals only |
| `brush poly align targets…` | M | ✓ (names / `BRUSH:idx`) | ✗ | touched → stdout; summary → **stderr** |
| `mover key add/move/rotate/remove/list <name>` | M/P | ✗ | ✗ | single mover; `--to/--by` on move/rotate |
| `level create/select/status` | M/P | ✗ | ✗ | human dashboards → stdout |
| `level materialize/preview` | build | ✗ | ✗ | writes artifact; "wrote …" → stdout |
| `level doctor` | P | ✗ | ✓ | `--severity/--category` |
| `event graph` | P | ✗ | ✓ (+`--dot`) | edges → stdout; lint+counts → **stderr** |
| `project show` | P | ✗ | ✓ | |
| `class list` | P | ✗ | ✗ | `--flat` = pipeable 1/line; tree default |
| `class show <fqcn>` | P | ✗ | ✗ | human category view |
| `stash capture [names…]` | M | ✓ (`--from-stdin`, T3D) | ✗ | id → stdout |
| `stash show/list/preview/drop/apply/promote/intersect/deintersect` | mixed | ✗ | ✗ | `--summary` on show; apply "applied N" → **stdout** |
| `prefab list/show/preview/apply/drop` | mixed | ✗ | ✗ | apply "applied N" → **stdout** |
| `texture sync/list/search/tags/classify status|set` | mixed | ✗ | ✗ | list/status/tags = TSV; search = refs 1/line |
| `substrate stub [pkg]` | build | ✗ | ✗ | |
| `cache clear` | M | ✗ | ✗ | |

---

## 2. Findings, ranked by severity

### H1 — `brush poly set` cannot consume `-`, breaking the `poly find | poly set` pipe its own sibling advertises
**Verbs:** `brush poly set` (cli 663–681; dispatch.py 2535–2559), `brush poly find` (cli 685–700).
`poly find`'s help reads *"print a brush's matching faces as BRUSH:idx selectors (feed to
poly align/**set**)"* (cli 686), and the intended loop is `poly find WALL --facing +Z | poly
set - --texture …`. But `poly set` takes only `targets` (`nargs="+"`, `BRUSH:SELECTOR`
positionals) and has **no `-`/stdin path** — dispatch passes `args.targets` straight to
`surface.apply_surface_edit` (2541). A piped `-` is parsed as a literal selector `-` (no
colon) and fails. Meanwhile `poly align` *does* accept `-` (dispatch.py 2600). So you can
`find | align` but not `find | set`.
**Rule violated:** "Mutating/consuming verbs read their target set from stdin via `-`" +
the help makes a promise the verb doesn't keep (a doc/behavior mismatch — clarity rule).
**Fix:** give `poly set` the same `_resolve_target_names`-style `-` handling `poly align`
has (accept `BRUSH:idx` lines and bare-name → all-polys), so `poly find | poly set -`
closes the loop. (Alternative, weaker: drop "/set" from `poly find`'s help — but that
abandons a genuinely useful pipe.)

### H2 — `actor move` is single-actor-only while its transform siblings `rotate`/`scale` take a set + `-`
**Verbs:** `actor move` (cli 349–356; dispatch.py 2642–2659) vs `actor rotate` (cli 416),
`actor scale` (cli 437). `move` takes a single `name` positional and cannot read `-`;
`rotate`/`scale` take `names…` **and** `-`. So `actor find --folder castle.props | actor
rotate - --by 0,90,0` works, but the exactly-parallel `… | actor move - --by 0,0,64`
does **not** — you must loop in the shell. `--by` over a set is unambiguous (each actor
moves by the delta, identical to `rotate --by`/`scale --by`), and `--to` over a set is the
same "all to one absolute value" semantics `rotate --to`/`scale --to` already allow.
**Rule violated:** "A verb over a SET takes the set, and that IS the operation" + mutators
read their set via `-`. `move` is the lone gap in the move/rotate/scale trio.
**Fix:** change `move` to `names… | -` (like rotate/scale), applying `--by` per-actor and
`--to` per-actor. (`brush clip`/`brush vertex move`/`mover key *` staying single is fine —
they are inherently single-brush/single-keyframe ops with no set-taking sibling.)

### M1 — Mutator success-summary destination is inconsistent (stdout vs stderr vs silent)
**Verbs:** `actor rotate` (dispatch.py 2927, 2957), `actor scale` (3006, 3039),
`actor order` (2697), `actor apply-transform` (3077), and `stash/prefab apply`
(`_apply_set`, dispatch.py 462) all print their human `"…ed N actor(s)"` line to
**stdout**. But `actor add` sends its count to **stderr** (2811) while emitting the
allocated names to stdout, and `actor delete`/`actor move` print **nothing**. Three
different conventions across peer mutators.
**Rule violated:** "Human summaries/counts go to stderr so they never pollute the pipe."
`actor add` follows it; the rotate/scale/order/apply-transform/apply family does not.
**Fix:** route every mutator's human summary to stderr (matching `add`/`bbox`/`poly
find`/`poly align`/`event graph`, which already do). Low blast radius — none of these
verbs emit pipe-consumable stdout data today — but it removes the inconsistency and future
-proofs any `verb - | …` chaining.

### M2 — `brush vertex list` lacks `--json` though its sibling `brush poly list` has it
**Verbs:** `brush poly list` has `--json` (cli 656; dispatch.py 2527); the peer
sub-element producer `brush vertex list` (cli 589; dispatch.py 2620) prints only a text
table. A script that wants welded-corner coordinates (to feed `vertex move --at`) must
scrape the table. `actor prop get` (structured effective values) and `mover key list`
similarly have no `--json`.
**Rule violated:** "Add `--json` where a script needs structured output." The gap is
sharpest for `vertex list` because its immediate sibling already has it.
**Fix:** add `--json` to `brush vertex list` first (there is already a `query`-layer
structure to serialize, mirroring `list_polys`); consider `actor prop get --json` and
`mover key list --json` as a follow-up.

### M3 — Generator prop-setting is asymmetric: `actor build --prop` exists, `brush build` has none
**Verbs:** `actor build` has `--prop KEY[.PATH]=VALUE` (repeatable, schema-validated,
cli 268–273); `brush build`'s shared `_common_build_opts` (cli 502–529) has no `--prop`.
So a point actor can be born with arbitrary props inline, but a brush/mover generator
cannot — you must `brush build … | actor add -` then a separate `actor prop set`. Both are
the same "stateless generator" family and both already accept `--rotate` (a `--prop`
shorthand), so the omission reads as an oversight rather than a deliberate split.
**Rule violated:** sibling-verb consistency (generator surface uniformity).
**Fix:** add `--prop` to `_common_build_opts` with the same grammar/validation as `actor
build --prop` (useful for mover-class actors that need e.g. `MoverEncroachType=` at birth).

### L1 — `--rotate` on generators vs `--to`/`--by` on the rotate verb
`actor build`/`brush build` set absolute orientation via a single `--rotate PITCH,YAW,ROLL`
(cli 274, 524), while `actor rotate` uses the `--to` (absolute) / `--by` (relative) pair.
Defensible — a fresh generator has no prior orientation, so only "absolute" is meaningful —
but a reader may expect `--rotate` to be relative, or expect the generator to spell absolute
as `--to`. **Fix (optional):** keep `--rotate` but ensure its help says "SET (absolute)"
(it does today); no code change strictly needed — flagged only for naming-uniformity
awareness.

### L2 — Terminal-mutator stdout noise: `brush clip` no-op message, `actor folder get` sentinel
`brush clip` prints `"clip plane did not intersect brush … — left unchanged"` to **stdout**
on a no-op (dispatch.py 3114) but is silent on success — a mutator emitting occasional
stdout chatter. `actor folder get` prints `(none)` for unfoldered actors (dispatch.py 213),
a non-name sentinel that pollutes a pipe if consumed. **Fix:** send `clip`'s no-op notice to
stderr; leave `folder get` as-is for humans but add `--json` (see M2) for scripts.

### L3 — `--catalog-dir` help depth varies across the texture verbs
`texture sync`'s `--catalog-dir` carries the full "(default: the resolved project's catalog
dir — the uedcli.toml `catalog` key, or `<root>/texture-catalog/`)" (cli 1027); the same
flag on `list`/`search`/`tags`/`classify status|set` is just `"tracked manifest dir"` (cli
1038, 1048, 1052, 1059, 1066). Every flag having a *real* help is satisfied, but the
terse variants drop the default-resolution detail. **Fix:** reuse the sync wording (or a
shared constant) so the help is uniform.

---

## 3. What is already consistent (verified — no action)

- **No `--union` / redundant set-flag anti-pattern anywhere.** `actor bbox` explicitly
  documents that the multi-actor case *is* the union (cli 327–333); `class list --all` was
  split into `--include-non-actor`/`--include-abstract`/`--depth all` (cli 912).
- **`--to`/`--by` symmetry holds** across `actor move`, `actor rotate`, `actor scale`,
  `brush vertex move`, `mover key move`, `mover key rotate` (absolute vs relative, same pair).
- **The `-` "sole source" convention is uniform** — mixing `-` with names errors, empty
  stdin is a clean no-op/exit 0 (dispatch.py `_resolve_target_names`, 127–146), and the two
  stdin dialects are kept distinct: **name list** (`find → delete/rotate/prop/order/folder
  -`) vs **T3D snippet** (`build → add -`, `build → brush replace -`).
- **`set|unset|get` sub-verb shape** is followed by both attribute editors
  (`actor prop`, `actor folder`).
- **Errors name the offending value and never traceback** — `dispatch()` funnels every
  domain exception to a clean exit 2 (dispatch.py 2156–2205): `Actor not found`, `texture
  not found: X`, `stash not found: 'X'`, `invalid level name: 'X'`, etc.
- **Grep-like exit semantics are uniform** for producers — zero matches exits 0 with empty
  stdout (`find`, `poly find`, glob `show`, `texture search`), an exact-name miss exits 2.
- **`find` is the stateless query verb**; filtering lives on `find` (`--class/--group/
  --name/--prop/--kind/--folder`), not sprinkled as per-mutator filter flags — the rubric's
  preferred shape.

---

## 4. Recommendations summary (future queue items, ranked)

1. **[high]** `brush poly set`: accept `-` (BRUSH:idx / bare-name stdin) so `poly find |
   poly set -` works — the pipe its own help promises. (H1)
2. **[high]** `actor move`: take `names… | -` like `rotate`/`scale`, applying `--by`/`--to`
   per-actor — close the move/rotate/scale trio. (H2)
3. **[medium]** Route every mutator success-summary to **stderr** (rotate/scale/order/
   apply-transform, stash/prefab apply) to match `actor add`. (M1)
4. **[medium]** Add `--json` to `brush vertex list` (then `actor prop get`, `mover key
   list`). (M2)
5. **[medium]** Add `--prop` to `brush build` (generator-surface parity with `actor
   build`). (M3)
6. **[low]** `brush clip` no-op notice → stderr; `actor folder get --json`. (L2)
7. **[low]** Unify the `--catalog-dir` help text across the texture verbs. (L3)

Each is a self-contained behaviour change; none block each other. H1 and H2 are the two
that break an advertised compose loop and are the highest-value.
