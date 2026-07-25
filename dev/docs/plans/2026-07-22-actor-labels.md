# Actor labels + `duplicate` overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. TDD each task. Steps use `- [ ]`.

**Goal:** Add a flat, multi-valued, uedctl-side `label` dimension to actors (per-actor `labels` sidecar; `actor label add|remove|clear|get`; `find --label`/`--no-label`; `actor add --label`; carrier round-trip), and overhaul `actor duplicate` (inherit labels + always a fresh `dup-<rand>`; `--label` additive; REQUIRED `--by`/`--at` placement).

**Architecture:** Labels mirror the existing single-valued `folder` dimension but as a **sorted set**. They ride the ONE shared per-actor T3D-tree path (`t3dtree.py`) on a new `labels` sidecar; live on `Actor.labels: frozenset[str]`; never emitted to the map. **Scope-cut (Andrzej):** THIS plan is **trunk + `duplicate` only** — NO stash/prefab `labels` channel; label verbs REJECT `--tree stash|prefab` (mirror the folder guard). The copy-between-trees spec will add the box channel later.

**Tech Stack:** Python 3.12, dataclasses, argparse, pytest via `bin/test`. **Spec:** `dev/docs/specs/2026-07-22-actor-labels.md` (symbol-anchored; read it for rationale). **Template to mirror:** the `folder` dimension — study these before starting: `uedctl/folderlib.py`, `t3dtree.py:200-263` (folder sidecar r/w), `dispatch.py:170-210` (`_reject_nonlevel_target_for_folders`, `_actor_folder`), `dispatch.py:1442-1458` (the delta-write diff + `_loaded_folders`), `_ingest_actor_t3d` `folder_override` (`dispatch.py:1789`), `model.py` `_FOLDER_CARRIER` + `Actor.folder`, `query.py` `list_actors`(`folders`/`no_folder`) + `actor_show_block`.

**Shared rules for EVERY task:** shared checkout on branch `uedctl-impl` with concurrent agents — commit ONLY the named files by explicit pathspec (never `git add .`/`-a`/dir); `git push` after each (rebase your own commits if the remote moved; never force-push/amend). Test from `Tools/uedctl` with `bin/test`. Short imperative commit subjects, no AI attribution. Errors name the offending value + exit 2 — never a traceback.

---

## SLICE 1 — Storage foundation (model, sidecar, delta-diff, labellib, carrier)

Deliverable: labels persist correctly through the trunk (the hard part is the delta-write trap).

### Task 1.1 — `Actor.labels` field + `folderlib.validate_segment`

**Files:** Modify `uedctl/model.py` (the `Actor` dataclass — add a field beside `folder`), `uedctl/folderlib.py` (export a segment validator). Test: `uedctl/tests/test_labellib.py` (NEW).

- [ ] Add `labels: frozenset[str] = frozenset()` to `Actor` (default empty; mirror how `folder: str | None = None` is declared).
- [ ] In `folderlib.py`, extract the single-segment charset check (the private `_SEGMENT` regex) into a public `validate_segment(s: str) -> None` that raises `ValueError(f"invalid segment: {s!r}")` on empty / non-`[A-Za-z0-9_+-]` / a `.`-containing token. Do NOT change existing folder-path validation (folders still allow their dotted paths); `validate_segment` is a new public helper. `validate_segment` MUST NOT reject a leading `-` (folders rely on the shared charset; the leading-`-` rule is labellib's, Task 1.2).
- [ ] Test: `validate_segment("lighting")` ok; `validate_segment("a.b")`, `validate_segment("")`, `validate_segment("a/b")` raise. Commit `uedctl/model.py uedctl/folderlib.py uedctl/tests/test_labellib.py`.

### Task 1.2 — `labellib.py` (validate, flat matcher, carrier)

**Files:** Create `uedctl/labellib.py`. Test: `uedctl/tests/test_labellib.py`.

- [ ] `validate_label(s: str) -> None`: calls `folderlib.validate_segment(s)` then rejects a leading `-` (`if s.startswith("-"): raise ValueError(f"label cannot start with '-': {s!r}")`).
- [ ] `match_label(pattern: str, label: str) -> bool`: reject `?`/`[`/`]` in `pattern` (`raise ValueError` — `*`-only, no char-class); then `fnmatch.fnmatchcase(label.casefold(), pattern.casefold())` (case-insensitive, works on Linux — do NOT use bare `fnmatch.fnmatch`). Only `*` is a wildcard.
- [ ] Carrier: `_LABELS_CARRIER = re.compile(r"^\s*//\s*uedctl-labels:\s*(.+?)\s*$")` and `format_labels_carrier(labels) -> str` returning `"    // uedctl-labels: " + ",".join(sorted(labels))` (comma-joined, sorted). Parsing splits the captured group on `,`, strips, drops blanks → a set.
- [ ] Tests: `validate_label("-x")` raises; `match_label("dup-*", "dup-a1")` True, `match_label("Torch*", "torch3")` True (case-insensitive), `match_label("a?", "ab")` raises (char-class rejected); carrier round-trips `{"b","a"}` → `// uedctl-labels: a,b` → `{"a","b"}`. Commit `uedctl/labellib.py uedctl/tests/test_labellib.py`.

### Task 1.3 — `labels` sidecar in `t3dtree.py` (sorted, atomic, remove-on-empty)

**Files:** Modify `uedctl/t3dtree.py` (`write_actor_tree` ~line 205, `read_actor_tree` ~line 261 — beside the `folder` block). Test: `uedctl/tests/test_t3dtree_labels.py` (NEW).

- [ ] In `write_actor_tree`, after the `folder` block, add a `labels` block mirroring it: if `actor.labels` non-empty, write `"\n".join(sorted(actor.labels)) + "\n"` to `<dir>/labels` atomically (`.labels.tmp<pid>` → `os.replace`); else `Path(d/"labels").unlink(missing_ok=True)` (so a cleared set truly removes the file).
- [ ] In `read_actor_tree`, after reading `folder`, read `<dir>/labels`: `frozenset(ln.strip() for ln in text.splitlines() if ln.strip())` (absent/empty → `frozenset()`) into `actor.labels`. **Do NOT change the returned tuple shape** — labels ride on `actor.labels`.
- [ ] Tests: write an actor with `labels={"b","a","c"}` → the file is exactly `a\nb\nc\n` (sorted); read back → `frozenset({"a","b","c"})`; empty labels writes NO file; writing an actor whose labels went empty REMOVES a pre-existing file. Commit the 2 files.

### Task 1.4 — the delta-write diff MUST include labels (the critical trap)

**Files:** Modify `uedctl/dispatch.py` (`TrunkLevelSource.__init__`/`load`/`save`, ~lines 1385-1458). Test: `uedctl/tests/test_labels_delta_write.py` (NEW).

- [ ] Add `self._loaded_labels: dict[str, frozenset[str]] = {}` in `__init__` (beside `_loaded_folders`).
- [ ] In `load()`, after the tuple unpack, build the baseline from the model: `self._loaded_labels = {n: level.actors[n].labels for n in level.actors}`.
- [ ] In `save()`, add a 4th clause to the `changed` set comprehension (currently body/rank/folder): `or level.actors[name].labels != self._loaded_labels.get(name, frozenset())`.
- [ ] In `save()`, after the write, re-derive the baseline beside `_loaded_folders`: `self._loaded_labels = {name: actor.labels for name, actor in level.actors.items()}`.
- [ ] Test (BOTH directions — this is the regression that catches the trap): load a level, add a label to an actor whose body/rank/folder are unchanged, `save()`, then confirm the on-disk `labels` file exists AND a fresh `read_actor_tree` shows the label; separately, clear an actor's labels and confirm `save()` removes the file. Assert the precondition (baseline lacks/has the label) before the mutation. Commit `uedctl/dispatch.py uedctl/tests/test_labels_delta_write.py`.

### Task 1.5 — the `// uedctl-labels:` carrier in `model.parse_t3d`

**Files:** Modify `uedctl/model.py` (`parse_t3d`, where `_FOLDER_CARRIER` is consumed). Test: `uedctl/tests/test_labellib.py` (or a model test).

- [ ] In `parse_t3d`, mirror the `_FOLDER_CARRIER` read: when a block line matches `labellib._LABELS_CARRIER`, parse the labels into the actor's `labels` set (and do NOT treat the `//` line as body). Import `labellib` at top of `model.py` (guard against circular import — if `labellib` imports `model`, it must not; keep `labellib` model-free).
- [ ] Test: `parse_t3d` of a block containing `// uedctl-labels: a,b` yields `actor.labels == {"a","b"}`. Commit.

---

## SLICE 2 — Query & verbs (`actor label`, `find --label`, `actor add --label`)

### Task 2.1 — `list_actors` labels/no_label filters + `actor_show_block` carrier

**Files:** Modify `uedctl/query.py` (`list_actors` — add `labels`/`no_label` params mirroring `folders`/`no_folder`; `actor_show_block` — emit the labels carrier and RENAME its `with_folder` param → `with_sidecars`, updating all callers). Test: `uedctl/tests/test_query_labels.py` (NEW).

- [ ] `list_actors(..., labels: list[str] | None = None, no_label: bool = False)`: an actor passes the labels filter if ANY of its labels matches ANY pattern (OR-within, via `labellib.match_label`); `no_label` matches only actors with an empty label set (mutually exclusive with `labels` at the CLI). AND with the other filters (same `_passes` structure).
- [ ] `actor_show_block`: rename the `with_folder` param to `with_sidecars` (it now gates BOTH carriers); when on and `actor.labels`, append `labellib.format_labels_carrier(actor.labels)` inside the block (alongside the folder carrier). Update EVERY caller of `actor_show_block` (grep for it — `duplicate`, `show`, etc.) to the new name. `--t3d-only` passes `with_sidecars=False`.
- [ ] Tests: `list_actors(lv, labels=["dup-*"])` returns only dup-labelled actors; `no_label=True` returns only unlabelled; `actor_show_block(a, with_sidecars=True)` emits `// uedctl-labels:` for a labelled actor and round-trips via `parse_t3d`. Commit `uedctl/query.py` + all touched callers + the test.

### Task 2.2 — `actor label add|remove|clear|get` (mirror `_actor_folder`)

**Files:** Modify `uedctl/cli.py` (a `label` subparser mirroring `folder`), `uedctl/dispatch.py` (`_actor_label` handler mirroring `_actor_folder`; a `_reject_nonlevel_target_for_labels` mirroring the folder guard; wire into `dispatch`). Test: `uedctl/tests/test_labels_verbs.py` (NEW).

- [ ] CLI: `actor label add|remove|clear|get`. `add`/`remove` take `<names…|->` positionals + repeatable `--label L`; `clear`/`get` take `<names…|->` (no `--label`); `get` gains `--json`. Each carries `_tree_flag`. (Mirror the `folder set --to` grammar but with repeatable `--label` and no `set`.)
- [ ] `_actor_label` handler: resolve names (`_resolve_target_names` + `resolve_actor_names`); reject `--tree stash|prefab` via `_reject_nonlevel_target_for_labels` (mirror the folder guard — labels are trunk-only THIS plan); **validate-all-then-apply** (validate every `--label` via `labellib.validate_label` AND resolve every name BEFORE any mutation); `add` = set-union, `remove` = set-difference, `clear` = empty set; write via the `LevelSource.save`. **PRODUCER:** print each touched actor Name to stdout (one per line), a human summary to stderr (mirror `actor rotate`'s producer pattern). `get` prints `Name<TAB>l1,l2` (sorted, comma-joined; unlabelled → `Name<TAB>(none)`), `--json` → `{name: [...]}`.
- [ ] Tests: `add` unions, `remove` subtracts (missing = no-op), `clear` empties + removes the file, `get` output shape (+`--json`); a bad `--label` (`-x` or `a.b`) or unknown name leaves ALL untouched (exit 2 naming it); `-` reads stdin, empty stdin → no-op exit 0; each mutating verb echoes touched Names to stdout; `--tree stash/x` → exit 2 "trunk only". Commit `uedctl/cli.py uedctl/dispatch.py uedctl/tests/test_labels_verbs.py`.

### Task 2.3 — `find --label` / `--no-label` + `actor add --label`

**Files:** Modify `uedctl/cli.py` (`find` gains `--label` (append) + `--no-label` in the existing folder mutex group's sibling; `actor add` gains repeatable `--label`), `uedctl/dispatch.py` (the `find` handler passes `labels`/`no_label` to `list_actors` + validates `--label` patterns; `_ingest_actor_t3d` gains a `labels_override` param SET BY THE ADD HANDLER ONLY). Test: extend `uedctl/tests/test_labels_verbs.py`.

- [ ] `find --label GLOB` (repeatable, OR-within; validate each pattern via `labellib.match_label`'s reject-path or a dedicated validate → exit 2 on `?`/`[`); `--no-label` (mutually exclusive with `--label`, mirror `--no-folder`).
- [ ] `actor add --label L` (repeatable): `_ingest_actor_t3d` gains `labels_override: frozenset[str] | None = None`; the ADD handler passes `labels_override=frozenset(args.label)` when given (OVERRIDES any carrier, mirroring `folder_override`); absent, the carrier (from `parse_t3d`) wins. Do NOT read `args.label` unconditionally inside `_ingest` — duplicate (Slice 3) also has `--label` and must NOT hit the override path.
- [ ] Tests: `find --label 'dup-*'` matches; repeated `--label` ORs; `--label` ANDs with `--folder`; `--no-label`; a `?`/`[` pattern → exit 2; `actor add --label lit` stamps every added actor; an explicit `--label` overrides a `// uedctl-labels:` carrier; the carrier alone round-trips via `show | add -`. Commit the 3 files.

---

## SLICE 3 — `duplicate` overhaul

### Task 3.1 — require `--by`/`--at`; always `dup-<rand>`; additive `--label`; placement translate

**Files:** Modify `uedctl/cli.py` (the `duplicate` parser: a REQUIRED mutually-exclusive `--by`/`--at` group; repeatable `--label`), `uedctl/dispatch.py` (the `duplicate` handler + `_ingest_actor_t3d` `labels_add` channel + the translate). Test: `uedctl/tests/test_duplicate_labels.py` (NEW).

- [ ] CLI: `duplicate` gains a **required** mutually-exclusive group of `--by X,Y,Z` (parse_coord) and `--at X,Y,Z` (parse_coord); a bare `duplicate` (neither) → argparse error / exit 2. Add repeatable `--label L`.
- [ ] `_ingest_actor_t3d` gains `labels_add: frozenset[str] | None = None` (a UNION channel, distinct from `labels_override`): each ingested actor's labels become `carrier_labels ∪ labels_add`. `actor add` never sets `labels_add`; `duplicate` never sets `labels_override`.
- [ ] `duplicate` handler: generate a fresh `dup-<rand>` via `t3dtree._rand_suffix` (expose it if needed for test injection), **re-rolled until it is not already a label anywhere in the target level**; pass `labels_add = {f"dup-{rand}"} | frozenset(args.label or [])` (always includes the dup token; `--label` is ADDITIVE). Copies inherit source labels via the `actor_show_block(with_sidecars=True)` carrier. Echo the batch label to stderr; keep printing new Names to stdout.
- [ ] Placement: apply `--by` (relative per-actor delta) or `--at` (anchor the set's bbox-min corner) using `stashlib.translate` + `writes.union_bounds` (NOT `_apply_set`) in the ingest path, before the trunk write.
- [ ] Tests: a bare `duplicate X` (no `--by`/`--at`) → exit 2; `duplicate X --by 128,0,0` offsets the copy; copies of a `lighting`-labelled actor carry `lighting` AND a `dup-<rand>` (matches `^dup-`); a pre-existing colliding `dup-…` forces a re-roll (inject the RNG); `--label wing-b` → copies carry inherited ∪ `dup-<rand>` ∪ `wing-b` (dup token STILL present); `--at` anchors the bbox-min corner; multi-actor `--by` preserves relative layout. Commit `uedctl/cli.py uedctl/dispatch.py uedctl/tests/test_duplicate_labels.py`.

---

## SLICE 4 — Docs

### Task 4.1 — user + dev docs

**Files:** Modify `docs/usage.md` (the `actor label` verbs, `find --label`/`--no-label`, `add --label`, the `duplicate` overhaul), `dev/docs/architecture.md` (the `labels` sidecar + `Actor.labels` + `_loaded_labels` delta baseline + `labellib.py` in the module map). Then update `dev/docs/board/`: cross off nothing (this is new) but note the plan is built.

- [ ] Document every new/changed surface in `docs/usage.md` with examples (mirror the folder docs). Note `duplicate` now REQUIRES `--by`/`--at`.
- [ ] Update `architecture.md`'s storage/module sections for labels.
- [ ] Commit each doc by explicit path.

---

## Self-review checklist
- Spec coverage: §2 storage (1.1,1.3), §3 delta-diff (1.4), §4 verbs (2.2), §5 find (2.3), §6 add+carrier (1.5,2.3), §7 duplicate (3.1), §9 module map (all), §11 decisions (grammar/no-set/`--label`/require-placement/always-dup/char-class-`*`-only). Scope-cut applied: NO §8 stash/prefab channel; label verbs reject `--tree stash|prefab`.
- No placeholders; the non-obvious code (delta-diff clause, `labels_add` vs `labels_override`, required placement, flat matcher, sorted sidecar) is spelled out; mechanical mirroring points at the folder template.
- Type consistency: `Actor.labels: frozenset[str]`; `labels_override`/`labels_add` params; `with_sidecars` rename applied to ALL `actor_show_block` callers; `match_label`/`validate_label`/`validate_segment` names consistent across tasks.
