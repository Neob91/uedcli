# Plan — expose `order_value` as a human-readable CSG rank

**Spec:** `dev/docs/board/to-spec/expose-order-value-as-a-human-readable-csg-rank/spec.md` (read it —
this plan argues from it).

**Goal:** a new CLI query verb `actor rank <names…|-> [--json]` and a `SceneActor.csg_rank: int` GUI
field, both computed as an actor's 1-based position in `level.order`.

## Global constraints

- Follow this codebase's TDD-first-failing-test style: write the test, watch it fail for the right
  reason, implement, watch it pass, commit.
- No fallbacks, no back-compat shims (`dev/docs/direction/conventions.md`) — this is a pure addition,
  nothing renamed or removed except the Inspector's visible `order_value` row (spec's explicit call).
- Every new flag/arg carries a real `help=`.
- Scope tests to the touched module while iterating (`bin/test -k actor_rank`, `-k serve`), full
  `bin/test` once before merge.

---

### Task 1: `actor rank` CLI verb

**Files:** Modify `uedcli/cli/parsers/actor.py` (new `rank` subparser, placed after `bbox`'s),
`uedcli/cli/commands/actor/routes.py` (add `"rank"` to the `("find", "show", "bbox")` routing tuple),
`uedcli/cli/commands/actor/query.py` (add `_rank`, dispatched from `run()`). Test: new
`uedcli/tests/test_actor_rank.py`, mirroring `uedcli/tests/test_bbox.py`'s fixture pattern
(`_project`/`_ns`/`_lexo` helpers, `trunk.write_level` with hand-assigned `order_value`s). Also
modify `uedcli/tests/test_tree_flag.py` (register `rank` in its central cross-verb `--tree`
parametrization) and regenerate `uedcli/tests/fixtures/parser_baseline/` (new subparser changes the
live argparse tree that file snapshot-tests).

**Interfaces:**
- `_rank(args, src) -> int` in `query.py`: resolve `args.names` via `target_names.resolve_target_names`
  (empty → return 0, no-op); `src.load()`; resolve to canonical names via
  `query.resolve_actor_names(level, raw)` (`KeyError` → print `e.args[0]` to stderr, return 2); dedupe
  order-preserving; build `positions = {n: i + 1 for i, n in enumerate(level.order)}`; print
  `f"{n}\t{positions[n]}"` per name in argument order (or a JSON object under `--json`); print a
  `f"rank of {len(names)} actor(s) ({len(level.order)} total)"` summary to stderr; return 0.

- [ ] **Step 1: failing tests** in `test_actor_rank.py`:
  - `test_rank_prints_name_tab_rank_in_argument_order` — 3 actors with hand-assigned `order_value`s
    giving a known `level.order`; request two names in an order that's NOT their CSG order; assert
    stdout lines are `Name<TAB>RANK` in the *requested* order, matching each actor's 1-based
    `level.order` position; assert the stderr summary line.
  - `test_rank_json` — `--json` on the same fixture; `json.loads(stdout)` equals
    `{"Door": 3, "Wall": 1}` (or whatever the fixture's actual ranks are).
  - `test_rank_unknown_name_exits_2` — one real + one bogus name; assert `rc == 2` and stderr contains
    `Actors not found:` and the bogus name; assert NO stdout (all-or-nothing).
  - `test_rank_empty_stdin_is_a_noop` — pipe `-` with empty stdin (via `target_names` monkeypatch or a
    stdin fixture matching how `test_bbox.py`/other stdin tests do it); assert `rc == 0`, no stdout.
  - `test_rank_dedupes_repeated_names` — the same name given twice; assert it prints once.
  - `test_rank_honours_tree_stash` — seed a stash entry (`stash_register`/`_seed_stash`-style helper,
    matching `test_tree_flag.py`'s pattern) with its own `order`, dispatch `actor rank <name>
    --tree stash/<id>`, and assert the printed rank matches that stash's `order` position, NOT the
    ambient trunk's — proves `--tree` actually routes rank off the ambient level, not just that the
    flag parses.
- [ ] **Step 2:** run `bin/test -k test_actor_rank`, verify FAIL. Since this test dispatches via a
  hand-built `argparse.Namespace` straight into `dispatch.dispatch(ns)` (the `test_bbox.py` pattern),
  it does NOT hit argparse's subcommand validation — it fails inside `actor_routes.run()`, which
  falls through the not-yet-added `"rank"` branch and returns `None`; `dispatch.py` then prints
  `unhandled verb: actor/rank` to stderr and returns 2. (Not an argparse/`AttributeError` — that
  would only show up going through `cli.build_parser().parse_args(...)`, which this test doesn't.)
- [ ] **Step 3:** implement the parser entry (help text per spec's sketch), the routes.py tuple
  addition, and `_rank` in `query.py`.
- [ ] **Step 4:** run, verify PASS.
- [ ] **Step 5:** add a `["actor", "rank", "X", "--tree", "stash/s"]` case to
  `test_tree_flag.py`'s `test_tree_flag_present_on_content_and_build_verbs` parametrization (next to
  `actor show`'s entry — a read verb otherwise stuck on the ambient level), so the flag's *acceptance*
  is centrally covered alongside Step 1's stash-routing behavior test. Run `bin/test -k tree_flag`,
  verify PASS.
- [ ] **Step 6:** regenerate the parser-baseline fixtures: `python -m uedcli.tests.parser_baseline`
  from the repo root, then `git diff --stat uedcli/tests/fixtures/parser_baseline/` to confirm only
  the expected help/action-tree files changed (the new `rank` entry under `actor`, nothing else). Run
  `bin/test -k parser_baseline`, verify PASS. **This step is not optional and not deferred to the
  pre-merge full suite** — `test_help_screens_match_baseline`/`test_action_tree_matches_baseline`
  would otherwise fail at merge time with no regeneration step having been run.
- [ ] **Step 7:** commit `feat: add actor rank query verb` (parser + routes + command + both test
  files + regenerated parser-baseline fixtures, one commit).

### Task 2: user docs — `docs/reference/actor/rank.md` + README row

**Files:** Create `docs/reference/actor/rank.md` (follow `bbox.md`'s shape: verb line, behavior
paragraph, output-shape paragraph, error/edge-case paragraph, "See also"). Modify
`docs/reference/actor/README.md` (add a `| [\`actor rank\`](rank.md) | query | print each actor's
1-based CSG-order position |` row next to the other query verbs).

- [ ] Write `rank.md` covering: the verb signature, what a rank number means (1-based position in
  `level.order`, rank 1 = evaluated/carved first), `-`/stdin + empty-stdin no-op, `--json` shape,
  the all-or-nothing unknown-name error, and a one-line pointer to `actor order` (the verb that
  *changes* this) and `actor find` (the usual way to build the `names` set). No user-facing doc may
  reference `order_value`'s internal LexoRank representation (`documentation.md`: user docs state
  facts plainly, no developer-doc pointers) — describe it as "CSG evaluation order", not "the
  order_value sidecar".
- [ ] Add the README table row.
- [ ] `bin/test -k test_doc_links` clean (the link/table checker runs over all of `docs/reference/`,
  not just board items — verify the new file and row satisfy it).
- [ ] Commit `docs: add actor rank reference page`.

### Task 3: `SceneActor.csg_rank` backend field

**Files:** Modify `uedcli/serve/scene.py` (`SceneActor` dataclass + `build_scene_payload`'s actor
loop). Test: extend `uedcli/tests/test_serve_scene.py`.

**Interfaces:**
- `SceneActor` gains `csg_rank: int`.
- `build_scene_payload`'s `for name in level.order:` becomes
  `for rank, name in enumerate(level.order, start=1):`; the `SceneActor(...)` call gains
  `csg_rank=rank`. `order_value` stays as-is (spec's explicit call: kept in the payload).

- [ ] **Step 1: failing test** — extend `test_build_scene_payload_has_polys_and_actors` (single-actor
  fixture: assert `room_actor.csg_rank == 1`) AND add a new
  `test_build_scene_payload_csg_rank_matches_level_order` using a 2-actor fixture (mirroring
  `test_scene_route_returns_200_with_a_json_safe_payload`'s two-actor `Level(actors=..., order=[...])`
  construction, i.e. one brush + one `Engine.Light`) with a known `order` list; assert each actor's
  `csg_rank` equals `order.index(actor.name) + 1` for both actors, and that `order_value` is still
  present and unchanged. **Use `_ued22_index()`, not the module-level `IDX = StubClassIndex()`, for
  this test** — the fixture's second actor is a non-brush actor (a `Light`), and `build_scene`
  resolves such an actor's class defaults via `index.resolver()`, which `StubClassIndex` does not
  implement (see this same test file's `_ued22_index()` docstring, and
  `test_scene_route_returns_200_with_a_json_safe_payload`, which already follows this rule for the
  same reason). Calling this out explicitly so a future pass doesn't "simplify" it back to `IDX`.
- [ ] **Step 2:** run `bin/test -k serve_scene`, verify FAIL (`AttributeError: csg_rank`).
- [ ] **Step 3:** implement the dataclass field + loop change.
- [ ] **Step 4:** run, verify PASS.
- [ ] **Step 5:** commit `feat: add SceneActor.csg_rank`.

### Task 4: frontend — `api.ts` type + `Inspector.tsx` display

**Files:** Modify `web/src/api.ts` (`SceneActor` interface), `web/src/panels/Inspector.tsx` (Order row).
Test: modify `web/src/panels/Inspector.test.tsx`.

**Interfaces:**
- `SceneActor.csg_rank: number` added to the interface (alongside `order_value: string`, kept).
- `Inspector`'s Order `<dd>` renders `actor.csg_rank` instead of `actor.order_value`.

- [ ] **Step 1: failing test** — update `Inspector.test.tsx`'s `fixtureActor()` to include
  `csg_rank: 3` (arbitrary, distinct from any other fixture number so a copy-paste mistake would show);
  in `"renders a fixture actor's property rows"`, replace the `expect(screen.getByText('m')).toBeTruthy()`
  assertion (the raw `order_value`) with `expect(screen.getByText('3')).toBeTruthy()` and add
  `expect(screen.queryByText('m')).toBeNull()` (the raw string must NOT appear — the spec's explicit
  drop-from-Inspector call).
- [ ] **Step 2:** run `npx vitest run Inspector`, verify FAIL (compile error: `SceneActor` missing
  `csg_rank`, or the raw string still rendering).
- [ ] **Step 3:** add `csg_rank: number` to the `SceneActor` interface in `api.ts`; change
  `Inspector.tsx`'s Order `<dd>` to `{actor.csg_rank}`.
- [ ] **Step 4:** run, verify PASS.
- [ ] **Step 5:** commit `feat: show csg_rank in the inspector`.

### Task 5: frontend fixture fallout — `api.test.ts` + `selection.test.ts` + `markers.test.ts`

**Files:** Modify `web/src/api.test.ts`, `web/src/scene/selection.test.ts`, and
`web/src/scene/markers.test.ts` (each has its own `SceneActor`-typed fixture literal/builder — grep
`SceneActor` under `web/src` for the full, current set before starting, since another in-flight
branch can add more between this plan being written and being built; all three gain `csg_rank`, since
Task 4 makes the field required).

- [ ] Run `npx tsc -b` in `web/` after Task 4; add `csg_rank: 1` (or any int) to each file's fixture
  builder until it's clean. No behavior in any of these tests depends on `csg_rank`'s value — this
  task is pure typecheck fallout, not new coverage.
- [ ] `npx vitest run` clean.
- [ ] Commit `chore: add csg_rank to test fixtures` (or fold into Task 4's commit if it lands in the
  same PR — call at merge time, not a blocker here).

---

## Verification (pre-merge)

- `bin/test -k actor` clean; `bin/test -k serve` clean; full `bin/test` once before merge.
- `npx tsc -b` clean in `web/`; `npx vitest run` clean in `web/`.
- Manual real-corpus check (spec's Verification section): a small fixture trunk over `uned/UED22`,
  `uedcli actor rank <names...>` printing sane ranks, `--json`, and the unknown-name exit-2 path, all
  exercised by hand once.
- `uedcli serve <fixture-level>` (per `building-features.md`'s exercise-the-app step): select an actor,
  confirm the inspector shows a plain integer rank and no raw LexoRank string.

## Self-review

- Every spec section (`actor rank`'s shape/output/errors, `csg_rank`'s backend field, the
  keep-`order_value`-in-payload/drop-from-Inspector call) maps to a task above. ✔
- No task depends on an interface a later task redefines: `csg_rank: int` (Task 3) is consumed by
  name in Tasks 4-5 unchanged. ✔
- Docs task (2) keeps `docs/reference/` current in the same change, per `documentation.md`. ✔
- The full-suite-only failure modes this plan could otherwise trip are pulled forward into the task
  that causes them, not left for a later merge-time surprise: Task 1 regenerates the
  `test_parser_baseline.py` fixtures in the same commit that adds the subparser (Step 6), and the
  spec's `--tree stash|prefab` claim is backed by a real test (Task 1's `test_rank_honours_tree_stash`)
  plus a `test_tree_flag.py` registration, not left as an assertion nobody checks. ✔
- Task 5's frontend-fixture list is gathered by grepping `SceneActor` at build time, not hardcoded
  against a possibly-stale snapshot of `web/src` — a fourth fixture site appearing before this plan is
  built (as `markers.test.ts` itself did) won't silently slip through. ✔
