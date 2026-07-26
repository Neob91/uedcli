# Spec — `--tree` flag + `$UEDCLI_LEVEL` env; drop `level select`

**Status:** reviewed (post-gate); ready to implement.
**Decisions recorded in:** `decisions.md` 2026-07-20 (this spec is ephemeral — the choices + rejected
alternatives live there). Supersedes the level-targeting decisions of 2026-07-05 19:07 / 19:28 and
reconciles the flag name from 2026-07-12 / 2026-07-19.
**Review gate:** two cold reviewers run 2026-07-20; all findings resolved into this revision (see §10).

---

## 1. Motivation

Two coupled problems with today's level targeting:

1. **The "selected level" is a machine-local pointer file** (`<root>/.uedcli/current-level`, set by
   `level select`, read by `level_select.resolve_level()` as the default source). The 2026-07-19
   CLI-usability probe proved it is a **live cross-session race**: a concurrent `level select`
   silently reflags it, so any verb defaulting to "the selected level" can read/write the *wrong*
   level with no error. `--target level/<name>` was the only race-safe workaround, retrofitted onto
   five read verbs to paper over it.

2. **`--target KIND/NAME` reads wrong.** "Target" connotes a *destination you aim output at*, yet on
   `stash capture` it names the **source**, and it collides conceptually with `materialize --out`.

**Fix (decided by Andrzej, 2026-07-20):**

- **Replace the pointer file with an ambient env var `$UEDCLI_LEVEL`** — per-process, so there is no
  shared mutable pointer to race on. Mirrors the existing `$UEDCLI_PROJECT` **precedence order**
  (flag > env > fallback); the value *grammar* differs (see §2).
- **Rename `--target` → `--tree`** — the value is a level / stash / prefab, which per the
  T3D-tree-consistency invariant (`decisions.md` 2026-07-18 23:01) are **one tree format**. This
  overturns July-12's rejection of `--t3d-tree` ("names the format, not the box") — now defensible
  precisely because the invariant made the three genuinely one tree.
- **Add `--tree` to the remaining level-using verbs** so *every* level-using verb resolves through one
  seam.
- **Drop `level select` entirely** (and `level create --select`). Setting the level is
  `export UEDCLI_LEVEL=<name>`. The eval-emitter form (`eval "$(uedcli level select foo)"`) was
  offered and **rejected** in favor of the clean drop (Andrzej, 2026-07-20).

### Named tradeoffs (documented, not blockers)

- **Ergonomics:** the pointer persisted across every terminal in a checkout (that persistence *was*
  the race); `$UEDCLI_LEVEL` persists only within one shell + its children — a new terminal / CI step
  re-exports. Accepted: the residual per-shell staleness is mitigated by §6 (the visibility echo).
- **Per-project scoping:** the pointer was per-root (`<root>/.uedcli/current-level`); `$UEDCLI_LEVEL`
  is per-shell and **global across projects**, with no cwd walk-up (unlike `$UEDCLI_PROJECT`). `cd` to
  another project in the same shell and a stale export bites — but it bites *loudly* (`level not
  found` under the new project's maps), not silently. Accepted.

---

## 2. Resolution model (the one seam)

Every level-using verb resolves through `_resolve_level_source(args)` with this precedence:

```
--tree KIND/NAME     (explicit, any of the three kinds)     ─┐
   else $UEDCLI_LEVEL (an ambient LEVEL name → level/<name>) ─┼─ first that resolves wins
   else  error        (see message below)                    ─┘
```

- **`--tree` value grammar is unchanged from `--target`:** `KIND/NAME`, `KIND ∈ level|stash|prefab`,
  NAME nested-allowed for stash/prefab, single safe segment for level. All existing validation in
  `_resolve_level_source` is retained verbatim; only the attribute/flag name changes (`target`→`tree`).
- **`$UEDCLI_LEVEL` is a bare LEVEL name only** (not `KIND/NAME`) — the "which level am I editing"
  ambient. stash/prefab work is always explicit via `--tree stash/… | prefab/…`.
- **Env-value normalization order (exact):** read → `strip()` → **blank ⇒ treat as unset** →
  `_check_safe_level(name)` → existence under `maps_dir`. A value containing `/` fails `_check_safe_level`;
  its error **hints the grammar**: `$UEDCLI_LEVEL is a bare level name, not KIND/NAME: <value>`.
- **The "no level" error names BOTH ways to set it** (Andrzej, 2026-07-20 — clean break, no legacy
  file read):
  ```
  no level: set the environment variable (export UEDCLI_LEVEL=<name>)
            or pass a level explicitly (--tree level/<name>)
  ```
- A malformed / nonexistent `$UEDCLI_LEVEL` errors loudly (exit 2) naming the offending value — never
  a silent empty-level read or a raw traceback. (`LevelSelectionError`/`_SelectionExit` are already
  caught at `dispatch.py` top-level → exit 2; §5 nails which layer owns each message.)

---

## 3. Module changes — `level_select.py`

The module becomes level-*resolution*, not a pointer store. File kept at `level_select.py` (no rename
this pass — avoids import churn; §9). Docstring rewritten.

| Symbol | Fate |
|---|---|
| `_pointer(root)` | **delete** — no pointer file. |
| `set_selected(...)` | **delete** — nothing sets a pointer. |
| `get_selected(root)` | **delete** — replaced by reading `$UEDCLI_LEVEL` at the dispatch layer. |
| `_check_safe_level(level)` | **keep** — the level-name validator (used by `--tree level/…` AND the env path). |
| `list_levels(maps_dir)` | **keep** — unchanged. |
| `resolve_level` | **rewrite** — new signature below; **does NOT read `os.environ` itself**. |
| `LevelSelectionError` | **keep.** |

**New signature (env passed IN, mirroring `config.resolve_project(env_project=…)`):**
```python
def resolve_level(*, env_level: str | None, maps_dir: Path) -> str:
    """Resolve the ambient level from $UEDCLI_LEVEL (passed in as env_level). strip; blank⇒unset;
    _check_safe_level; must exist under maps_dir. Raises LevelSelectionError (→ exit 2) otherwise."""
```
`root` param dropped — all four live callers (`dispatch.py:1305,1787,1891,1905`) already hold
`maps_dir`, and the only `root`-consumers (`get_selected` at 1583/1629/1658) are deleted/rewired. The
caller supplies `env_level=os.environ.get("UEDCLI_LEVEL")`.

The stale `.uedcli/current-level` file, if left from a prior checkout, is **ignored** (gitignored
throwaway) — no migration/cleanup step, no read of it (clean break).

---

## 4. Verb-by-verb

### 4a. Rename every `args.target` read site — NOT just the seam

`--target` is read in **more than one place**. The rename (`--target`→`--tree`, `args.target`→
`args.tree`, and the embedded `--target …` message strings) must cover ALL of:

| Site | File:line | What it does | Risk if missed |
|---|---|---|---|
| `_resolve_level_source` | dispatch.py:1267 | the resolution seam | wrong default source |
| `_reject_nonlevel_target_for_folders` | dispatch.py:174 | rejects stash/prefab on folder verbs | **`getattr(args,"target",None)` → None → guard silently never fires** |
| `_reject_nonlevel_target_for_order` | dispatch.py:203 | rejects stash/prefab on order verbs | same silent-regression |
| `actor add` source-mixing check | dispatch.py:262 | rejects `--target` + stdin/T3D mix | silent mis-accept |
| `_target_flag` (parser) | cli.py:153 | the flag definition + help | — |
| any embedded `--target stash|prefab` message strings | (the 3 guards) | user-facing text | stale text |

**Action:** grep `args.target` / `getattr(args, "target"` and rename EVERY hit (5 code sites beyond
the parser) plus their message strings. The ~34 mutating verbs + 5 read verbs pick up the env default
for free once the seam is renamed.

### 4b. The holdouts — add `--tree`, level-kind-only, mode-aware

| Verb | Today | After |
|---|---|---|
| `level materialize` | `resolve_level` direct (1787) | `--tree` (LEVEL kind only) → env → error. |
| `level preview` (trunk mode) | `resolve_level` direct (1891/1905) | `--tree` (LEVEL kind only) → env → error. |
| `level preview` `--map` / `--list-actors` | no level resolved (gated on `args.map is None`, 1889) | **unchanged — no level resolved.** `--tree` + `--map` is contradictory → reject exit 2. |
| `level status` | direct `get_selected` at 1658 + dead `level select` hint at 1662 | rewire: read `$UEDCLI_LEVEL`; "nothing set" hint → `export UEDCLI_LEVEL=…`. |
| `level list` | reads pointer to mark active (1629/1640-1645) | mark from the **raw** `$UEDCLI_LEVEL` (unvalidated); compute listed/stale itself; **swallow ALL resolution failures** (unset AND malformed) → mark nothing. Never crash `list` on a bad env. |

**materialize/preview accept the `level` kind ONLY.** `--tree stash/…`/`prefab/…` → clear exit-2
("materialize/preview operate on a level; use `stash preview` / `prefab preview`"). Rationale: a
captured actor-set has no world/`LevelInfo` to build or walk, and dedicated `stash|prefab preview`
already exist. (Open Q #1 → **closed: reject**.)

**Helper `_resolve_level_only(args)`** runs the seam resolution, errors if the resolved kind ≠ `level`,
and **returns the level NAME** (via the source's `display_name`, as `level status` already uses at
1674) — because `_level_preview` passes `level_name=name` into `render_shots` (1896) and materialize
builds `TrunkLevelSource(maps_dir/name)`. The helper must surface the name so those two keep working;
otherwise `--tree level/NAME` never actually reaches them.

**materialize/preview `--help`:** the shared `_tree_flag` help advertises `level|stash|prefab`, which
those two reject. Give materialize/preview a **verb-specific one-liner** noting "level only" (or a
`_tree_flag(p, level_only=True)` variant) so `--help` doesn't promise a kind that exit-2s.

### 4c. Deletions

- `level select` parser + `_level_select` dispatch handler.
- `level create --select` flag + its `set_selected` call (`level create` still creates the dir).
- `set_selected` / `get_selected` / `_pointer` (§3).

## 5. Error ownership & exception taxonomy

- `level_select.resolve_level` raises **`LevelSelectionError`** with the §2 "no level" / malformed
  messages. Callers that *swallow* (only `level list`) catch **`LevelSelectionError` specifically**
  (not a bare `except`) so an unrelated error never gets eaten.
- `_resolve_level_source`'s `--tree`-grammar and kind errors stay **`_SelectionExit`** (unchanged).
- Both types already reach the top-level handler → exit 2. No raw traceback for any bad value.

## 6. Visibility echo on mutations (Andrzej, 2026-07-20 — "yes")

When a **mutating** verb resolves its level from the **ambient env** (i.e. `--tree` was NOT given and
the env fallback was used), emit ONE line to **stderr** (pipe-safe, per the CLI ethos of human notes
→ stderr):
```
editing level 'castle' (from $UEDCLI_LEVEL)
```
- **Only mutating verbs** (they *write*): the `actor …`/`brush …`/`mover …`/`poly …` write paths,
  `stash capture`, `actor add`, materialize (it writes a map). **Not** pure reads (`find`, `show`,
  `bbox`, `poly list/find`, `status`, `list`, `doctor`, `event graph`, preview) — a read echoing its
  own target is noise.
- **Suppressed when `--tree` is explicit** — the user already named the target, no surprise to warn
  about.
- Implementation seam: the echo belongs where mutation + default-resolution meet. Cleanest is for the
  resolution helper to return *whether* the source came from the env fallback (a flag), and the
  mutating dispatch paths emit the line. Must NOT fire for reads → so it's opt-in per mutating verb,
  not baked into `_resolve_level_source` unconditionally. **Detail to settle in implementation:** the
  exact list of "mutating" entry points; err toward the write verbs enumerated above.

## 7. Impact — docs

- **`architecture.md`** — `level_select` module description; the `.uedcli/` state list (drop
  `current-level`); the resolution-seam + env description; the visibility echo.
- **`direction.md`** — the safety/state section lists "the selected-level pointer" under `.uedcli/`
  throwaway state → replace with the ambient `$UEDCLI_LEVEL` framing (env, not in-tree state).
- **`decisions.md`** — new 2026-07-20 entry (choice + the rejected eval-emitter + the `--t3d-tree`
  rebuttal + the two named tradeoffs + the echo + clean-break migration); supersede 2026-07-05 19:07 +
  19:28; reconciling note on 2026-07-12 / 2026-07-19 (flag renamed).
- **`usage.md`, `docs/README.md`, `unrealed/commands.md`** — every `level select` / `--target`
  example → `export UEDCLI_LEVEL=…` / `--tree`.
- **Docstrings** — `_resolve_level_source` (dispatch.py:1261) and `_target_flag`→`_tree_flag`
  (cli.py:154-162) both narrate the pointer model; rewrite both (add to the sweep by name).
- **`board/`** — driving inbox/to-spec item → `done.md`; any deferred remnant → a new line.
- Stale `plans/`/`specs/`/`reviews/` are ephemeral — not retro-edited except where actively
  misleading.

## 8. Impact — tests

~30 modules reference `--target` / `level select`.

- `level select <name>` setup → `monkeypatch.setenv("UEDCLI_LEVEL", name)` **per-invocation** (proper
  teardown — never a bare `os.environ[...] =` that leaks across tests and re-creates a global-mutable
  race in the suite itself).
- `--target …` → `--tree …`; `test_target_flag.py` → `test_tree_flag.py`.
- `test_level_select.py` → env-resolution tests.
- **New regressions:** (a) precedence flag > env > error; (b) malformed/nonexistent env → exit 2
  naming the value; (c) blank/whitespace env → "no level"; (d) `/`-containing env → grammar-hint
  error; (e) materialize/preview reject `--tree stash/…`; (f) `preview --map` with no env does NOT
  error; (g) `level list` with a malformed env does NOT crash (marks nothing); (h) the mutation echo
  fires from env, is silent with explicit `--tree`, and is silent for reads; (i) the three
  non-level-kind guards still fire under `--tree` (regression against R1); (j) no `level select` /
  `--target` residue in any `--help` (extend `test_help_completeness` / `test_cli_consistency`).
- `bin/test` green before commit.

## 9. Out of scope

- Renaming the `level_select.py` module file (kept to avoid import churn; revisit later — Open Q #2 →
  deferred).
- Any change to the `KIND/NAME` grammar or to stash/prefab resolution.
- A `level select`-style "print current level" convenience (dropped; `echo $UEDCLI_LEVEL` /
  `level status` suffice).
- Reading the legacy `.uedcli/current-level` for a migration hint (clean break — Andrzej).

## 10. Review-gate resolutions (2026-07-20)

- **R1** args.target undercount → §4a enumerates all 5 code sites + message strings.
- **R2** preview `--map`/`--list-actors` no-level → §4b carve-out.
- **R3** `level status` dead `get_selected`/hint → §4b rewire.
- **R4/S3** `level list` reads raw env, swallows all failures → §4b.
- **R5/S-grammar** "mirrors exactly" softened to precedence-only; `/`-hint → §2.
- **R6** helper surfaces name → §4b.
- **S2** `resolve_level(env_level=…)` param, no internal `os.environ` → §3.
- **S4** exception taxonomy → §5.
- **B1 (eval-emitter)** → already rejected by Andrzej (drop chosen over emit); recorded in decisions.
- **B2 (visibility echo)** → adopted → §6.
- **S1 (per-project scoping) / ergonomics** → named tradeoffs, §1.
- **S5 (`--tree` overturns `--t3d-tree`)** → acknowledged in §1 + decisions ledger.
- **S6 (migration)** → clean break, error names both set-methods (§2); no legacy-file read.
- **S7 (materialize/preview help)** → verb-specific "level only" help, §4b.
- **N2** env normalization order → §2. **N3** test env hygiene → §8.
- Open Qs: #1 reject (closed), #2 defer module rename, #3 keep-and-read-raw-env.

## 11. Post-build review gate (2026-07-20, two cold reviewers)

Both reviewers reported **no blockers and no correctness bugs**; they independently verified the
uniform resolution, the echo seam covering all 18 trunk mutations via `save()` (+ explicit
materialize/capture), the guards reading `args.tree`, normalization, exit taxonomy, and that the race
is fully gone. Resolved:
- **`--tree ""` silently fell back to env** (both) → now `if tgt is not None:` in both resolvers +
  `target is None` in `level status`; an explicit empty flag errors "must be KIND/NAME". Regressions
  added (`test_env_level_and_echo.py`).
- **`config.py` docstring left ungrammatical** by the pointer-removal edit (reviewer 1) → fixed.
- **eventgraph no-level test asserted only `== 2`** (reviewer 2) → now also asserts the message.
- Accepted as-designed: preview (a read) doesn't echo while materialize does; `{"selected": null}`
  status sentinel; materialize's idempotent double project-resolve; `resolve_level` `is_dir` vs
  `list_levels` `actors/` leniency (unusual, harmless).

Full offline suite green after fixes: **1981 passed, 1 skipped, 1 xfailed** (+ 53 Rust). End-to-end
smoke confirmed the echo, the explicit-`--tree` suppression, the empty-`--tree` error, and the
materialize stash/prefab rejection through the real `bin/uedcli` binary.
