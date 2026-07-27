# Spec: unify the stash, prefab, and trunk on-disk T3D trees onto ONE per-actor format

**Status:** design (spec review gate passed). Ephemeral — fold the durable outcome into
`architecture.md`/`usage.md` on build, then this file may be deleted.

**Binding decision (do NOT re-litigate):** `decisions.md` **`2026-07-18 23:01 UTC — INVARIANT:
stash, prefab, and trunk MUST share ONE T3D tree format`**. All three on-disk T3D trees — the git
**trunk** (`maps/<level>/`), a **stash** entry (`.uedcli/stash/<id>/`), and a library **prefab**
(`<prefabs-dir>/<name>/`) — MUST use the trunk's per-actor layout
`actors/<name>/{actor.t3d, order_value[, folder]}` (per-actor directory; per-actor LexoRank
`order_value` sidecar; optional per-actor `folder` sidecar; **no shared `order` file**), read/written
through ONE shared code path. Any per-tree extras (a stash/prefab `meta.json` — capture anchor,
timestamp — and a `packages` list) sit BESIDE the shared `actors/` tree. Rationale for extending the
per-actor form to stash/prefab (which don't strictly need merge-freedom): one format, one code path,
and prefabs being git-committed benefit from conflict-free merges too (see that entry + the
`2026-07-01 07:05 UTC` git-merge/`order_value` spike). **This spec designs HOW.**

---

## Open sub-choices for Andrzej

### (1) HEADLINE — prefab migration path (prefabs are GIT-COMMITTED library artifacts)

Existing prefabs in a project's `<prefabs-dir>/` are in the **old single-blob** format
(`<name>.t3d` = one `Begin Map` blob + `<name>.json` sidecar). After this change a prefab is a
**directory** `<name>/{actors/<name>/…, packages, meta.json}`. The two formats are trivially
distinguishable on read (old = a **file** `<name>.t3d`; new = a **dir** `<name>/` containing
`actors/`), so any option is implementable cleanly. In the LUM repo the committed prefabs are just
`Prefabs/x.t3d` + `Prefabs/x.json` today, but the tool is generic-UE1 and prefabs are meant to be
shareable across uncoordinated projects, so "there are only a couple" is not a safe global
assumption.

- **(A) Auto-convert on read** — `read_prefab` detects the old file form and reads it (parse the
  `Begin Map` blob, split into actors); the next `write_prefab` (e.g. a `--target prefab/…` edit, or
  an explicit `prefab migrate`) writes the new dir form **and deletes the stale `<name>.t3d` +
  `<name>.json`**. Zero user action; existing committed content never breaks. Cost: a small
  old-format reader lingers in the codebase until every prefab everywhere is known-migrated (never
  provable for a distributed library), so in practice it stays.
- **(B) One-time bulk `prefab migrate` verb** — an explicit command that rewrites every old-format
  prefab under the library root to the new form in one shot (one clean git commit, no lingering
  dual-read). Cost: a manual flag-day step; an un-migrated old prefab read *before* the user runs it
  must still do *something* — either error clearly ("run `prefab migrate`") or silently fall back to
  reading old (which is just option A again). A pure B with a hard error on un-migrated reads is the
  cleanest code but the worst ergonomics.
- **(C) Hard cutover** — old prefabs simply stop loading; the user re-captures them. Simplest code,
  but it **breaks existing git-committed content**, which conflicts with the project's "never
  irretrievably clobber authored work" safety principle (`direction.md` Safety).

**RECOMMENDATION: (A) auto-convert-on-read, with the stale `<name>.t3d`/`<name>.json` removed on the
next save — AND ship a thin `prefab migrate` verb (B) as an optional explicit bulk path.** Reasoning:
(A) is the safety net that guarantees no git-committed prefab ever breaks and needs zero user action
— directly serving the never-clobber principle; the old-format reader is genuinely tiny (a `Begin
Map` blob split is a handful of lines) and self-contained, so its lingering cost is low. (B) layered
on top gives a user who wants a single clean flag-day commit an explicit, greppable path instead of
lazy conversion scattered across future saves. **(C) is rejected** — breaking committed content for a
code-cleanliness gain is the wrong trade for a durable, shareable artifact. This is THE decision to
confirm with Andrzej before build; record the choice in `decisions.md`.

### (2) Do captured stash/prefab members carry a per-actor `folder` sidecar?

The shared format has an optional `folder` sidecar per actor. Today captured sets carry **no** folder
(`stashlib.with_folder`'s docstring: the flat tree "has no sidecar slot"), and `stash/prefab apply
--folder` stamps the folder on **placement into the trunk** (mirroring how a captured `Group` is
treated as meaningless and re-set on apply). Now the slot exists, so we *could* persist it.

- **(a) Do NOT persist folder on capture (recommended).** The shared writer still supports the
  `folder` sidecar uniformly (it's shared code), but capture/promote leave each captured member's
  `folder = None`, so no `folder` file is written. `apply --folder` keeps its current
  placement-stamp meaning. This preserves today's semantics exactly and keeps capture parity with
  `Group` (a captured organization path is meaningless in a new destination).
- **(b) Preserve folder on capture.** A stash captured from a trunk subtree would keep its
  `castle.tower.*` organization. Arguably useful for capturing a labelled sub-build, but it collides
  with `apply --folder`'s "replace on placement" model (which wins?) and is a behavior change. **It
  is also NOT a free toggle:** the wrapper currency is `full_level: dict[name→T3D blob]`, and a T3D
  blob carries NO folder (folder is a uedcli-side sidecar, never in T3D). So (b) requires a new
  folder channel through capture → `write_stash`/`write_prefab` (a signature change §1 otherwise
  keeps unchanged) — e.g. an extra `folders: dict[name→str|None]` arg. That extra cost is part of the
  choice.

**RECOMMENDATION: (a) — do not persist folder on capture; keep `apply --folder` as the sole
placement-time stamp.** Under (a), captured members are `folder=None` (`_level_from_blobs` sets it),
so stash/prefab simply write **no `folder` file** — no wrapper signature change, and today's
semantics preserved exactly. This is **low-stakes / not load-bearing** for the build, but it is NOT a
pure default-flip (see (b)'s signature cost), so it is worth an explicit answer. Flagged for Andrzej
to override only if he wants captured subtrees to retain organization (and accepts the extra channel).

---

## Background: the three current formats (what we're collapsing)

| Tree | Module | On-disk today | Body form | Order | Extras |
|---|---|---|---|---|---|
| **trunk** | `trunk.py` | `actors/<name>/{actor.t3d, order_value[, folder]}` | `dump_actor_body` (Name= stripped, brush model-ref → constant `Model`; re-injected from dir name on read) | per-actor `order_value` LexoRank sidecar | none |
| **stash** | `stash_register.py` (via `tree_io.read_state_dir`) | `<id>/{actors/<name>.t3d, order, packages, meta.json}`; filenames `safe_name`/urllib-quoted; whole-tree atomic swap via `.staging/` + `os.replace` | canonical T3D blob **with** Name= | **shared `order` file** | `packages`, `meta.json` (anchor, ts) |
| **prefab** | `stashlib.py` | `<name>.t3d` (one `Begin Map` blob) + `<name>.json` | canonical blobs **with** Name= inside one Map | `order` key inside the JSON | `packages` + `meta` folded into the SAME JSON |

The target is: **all three use the trunk row.** The stash's flat `actors/<name>.t3d` +
`safe_name`-quoting + shared `order` file, and the prefab's single-blob + one-JSON form, are both
replaced by the per-actor tree. The stash/prefab extras (`packages`, `meta.json`) move to **siblings
of `actors/`** (the prefab's single JSON is split — see §2).

---

## 1. The shared per-actor tree module/API

**Create `uedcli/t3dtree.py`** (name chosen so it reads as "the T3D per-actor tree", not "trunk" or
"level" — stash/prefab are neither). It houses the per-actor tree I/O **already present in
`trunk.py`**, moved verbatim so there is exactly ONE implementation:

- the rank algebra (`rank_between`, `ranks_between`, `initial_ranks`, `append_rank`,
  `duplicate_ranks`),
- the random-suffix name allocator (`alloc_name`, `_rand_suffix`),
- the body strip/inject (`dump_actor_body`, `load_actor_body`, `_MODEL_CONST`, the `_NAME_HDR` /
  `_NAME_TRAILER` regexes),
- the safe-segment guard, **renamed public** `check_safe_segment` (today `_check_safe_segment`),
- the tree read/write core, renamed to tree-neutral names:
  - `write_actor_tree(tree_dir, level, ranks, *, deleted=frozenset(), only=None)` — **exactly**
    today's `write_level` body (writes `<tree_dir>/actors/<name>/{order_value, actor.t3d[, folder]}`,
    per-actor atomic, delta-capable via `only`/`deleted`).
  - `read_actor_tree(tree_dir) -> (Level, ranks, bodies, folders)` — **exactly** today's
    `read_level_with_bodies`.

**`trunk.py` keeps its level-facing names as thin re-exports/wrappers** so its many callers and tests
(`read_level`, `read_level_with_bodies`, `write_level`, `append_rank`, `alloc_name`, `rank_between`,
…) do NOT churn:

```python
# trunk.py
from .t3dtree import (write_actor_tree as write_level, read_actor_tree as read_level_with_bodies,
                      rank_between, ranks_between, initial_ranks, append_rank, alloc_name,
                      dump_actor_body, load_actor_body, check_safe_segment, duplicate_ranks)
def read_level(level_dir):                     # unchanged 2-tuple convenience wrapper
    level, ranks, _b, _f = read_level_with_bodies(level_dir)
    return level, ranks
```

(Equivalently, keep the code physically in `trunk.py` and import it from `stash_register`/`stashlib`
as `from .trunk import …`. **Recommend the dedicated `t3dtree.py` module** — the decision names it "a
shared code path", and a stash/prefab importing from a module literally called `trunk` is a
misdirection. Either satisfies the one-implementation invariant; this is an internal placement call,
not a behavior choice.)

### The sibling-metadata payload (the per-tree extras)

Add two small helpers in `t3dtree.py` for the `packages` + `meta.json` that sit **beside** `actors/`
(the trunk simply never calls them):

```python
def write_sidecars(tree_dir, *, packages: list[str], meta: dict) -> None:
    # <tree_dir>/packages  = "\n".join(packages) + trailing "\n" if non-empty
    # <tree_dir>/meta.json = json.dumps(meta, sort_keys=True)
def read_sidecars(tree_dir) -> tuple[list[str], dict]:
    # missing files → ([], {})   (mirrors read_stash's all-empty-on-missing contract)
```

**Signature summary of the shared path:** the tree I/O is `(Level, ranks, folders-inside-Level)` in,
`(Level, ranks, bodies, folders)` out — the actors dict + per-actor LexoRank ranks + optional
per-actor folder (carried on `Actor.folder`, so no separate arg). The caller-supplied SIBLING payload
(`packages`, `meta`) is written/read by the separate `write_sidecars`/`read_sidecars` — cleanly
orthogonal to the actor tree.

### How stash/prefab become thin wrappers

**`stash_register.FileStashRegister` — signatures UNCHANGED** (so `dispatch.py`, `_dispatch_stash`,
and all mocks in `test_generators.py` keep working):

```python
def write_stash(self, stash_id, *, full_level: dict[str,str], order: list[str],
                packages, meta, force=False) -> str:
    validate_member_name(stash_id)
    dest = self.root / stash_id
    if dest.exists() and not force: raise FileExistsError(...)
    prior = _read_ranks_if_present(dest)                 # {name: order_value} from existing tree
    level = _level_from_blobs(full_level, order)         # parse each blob → Actor, keep `order`
    ranks = _ranks_for(order, prior)                     # preserve surviving; append-mint new (§ below)
    staging = mkdtemp(under self.root/.staging)
    t3dtree.write_actor_tree(staging, level, ranks)      # writes staging/actors/<name>/…
    t3dtree.write_sidecars(staging, packages=packages, meta=meta)
    atomic-swap staging → dest (rmtree dest first, os.replace)  # unchanged whole-tree swap
    return stash_id

def read_stash(self, stash_id) -> (dict[str,str], list[str], list[str], dict):
    dest = self.root / stash_id
    if not dest.is_dir() or _is_stale_flat_stash(dest):  # unknown OR pre-migration flat → all-empty
        return {}, [], [], {}
    level, ranks, _bodies, _folders = t3dtree.read_actor_tree(dest)
    full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order}  # blobs WITH Name= (as today)
    packages, meta = t3dtree.read_sidecars(dest)
    return full, level.order, packages, meta
```

- `exists`, `list_stashes`, `drop_stash` are **unchanged** — they key on `meta.json`, which still
  sits beside `actors/`. An emptied-but-real stash and nested ids keep working exactly as today.
- The `full_level` dict the wrapper accepts still carries canonical blobs **with** `Name=`; the
  wrapper's `_level_from_blobs` parses them to `Actor`s and `write_actor_tree`'s `dump_actor_body`
  strips the identity tokens — so the **stored** `actor.t3d` is byte-identical to the trunk's (this
  is what the consistency test §6 pins). `read_stash` re-emits `canonical_actor_t3d` (Name= back from
  the dir name) so **downstream consumers are unchanged** (they still get `{name: blob-with-Name}`).

**`stashlib.write_prefab` / `read_prefab` / `list_prefabs`** become the analogous wrappers, with the
prefab-specific path handling:

```python
def write_prefab(root, name, *, full_level, order, packages, meta, force=False) -> None:
    validate_member_name(name)
    root = Path(root).resolve()
    dest = (root / name).resolve()
    if not dest.is_relative_to(root):                    # containment guard, now on the DIR
        raise ValueError(f"prefab name escapes the library root: {name!r}")
    if dest.exists() and not force: raise FileExistsError(...)
    # …identical body to write_stash: prior ranks (_read_ranks_if_present(dest)), _level_from_blobs,
    # staging swap, write_sidecars… (staging under root/.staging so an interrupted write can't
    # leave a half prefab dir).
    # THEN, after the swap lands, remove any stale OLD-format files (§(1)A migration cleanup):
    (Path(root) / f"{name}.t3d").unlink(missing_ok=True)
    (Path(root) / f"{name}.json").unlink(missing_ok=True)
    # Ordering is deliberate: swap-first, unlink-after. read_prefab is NEW-DIR-WINS, so a crash
    # between the two leaves a shadowed-but-harmless old file that the next save cleans up.

def read_prefab(root, name) -> (dict, list, list, dict):
    dest = Path(root) / name                             # NEW dir  (Path(root)/name/actors/…)
    old_t3d = Path(root) / f"{name}.t3d"                 # OLD file  (Path(root)/name.t3d)
    # NEW-DIR-WINS precedence: if the new dir exists, read it and IGNORE any leftover old file.
    # A crash between the migration swap and the old-file unlink (§(1)A) therefore self-heals — the
    # new dir shadows the stale file on every read, and the next save re-attempts the unlink.
    if not dest.is_dir() and old_t3d.is_file():          # old format ONLY when no new dir is present
        return _read_old_prefab(root, name)              # parse Begin Map blob + <name>.json (§(1)A)
    level, ranks, _b, _f = t3dtree.read_actor_tree(dest)
    packages, meta = t3dtree.read_sidecars(dest)
    full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order}   # level.order == the sort
    return full, level.order, packages, meta

def list_prefabs(root) -> list[str]:
    # A NEW prefab is a DIR carrying meta.json (like list_stashes), at any depth (nested names).
    # An OLD prefab is a <name>.t3d FILE with NO `actors` component anywhere in its path (so a
    # new-tree actor.t3d at <name>/actors/<actor>/actor.t3d is NEVER miscounted). `.staging` (in-flight
    # writes) is skipped so a half-written prefab's meta.json can't surface.
    root = Path(root)
    def _staged(p): return ".staging" in p.relative_to(root).parts
    new = {p.parent.relative_to(root).as_posix() for p in root.rglob("meta.json") if not _staged(p)}
    old = {p.relative_to(root).as_posix()[:-4] for p in root.rglob("*.t3d")
           if "actors" not in p.relative_to(root).parts and not _staged(p)}
    return sorted(new | old)
```

**Wrapper helper contracts** (shared by both wrappers, in `stashlib.py` or a small private module):

- `_read_ranks_if_present(dest) -> dict[str,str]` — reads `{name: order_value}` from an existing
  per-actor tree at `dest` (via `read_actor_tree`), `{}` if `dest` is absent OR is an old-format
  prefab (no per-actor sidecars). On the first old→new prefab convert this returns `{}`, so ranks are
  minted fresh in `order` sequence — acceptable (there were no per-actor ranks to preserve).
- `_level_from_blobs(full_level, order) -> Level` — `parse_t3d` each blob, assemble a `Level` whose
  `actors` are the parsed `Actor`s (each `folder=None` — a blob carries no folder, see §4) and whose
  `.order` is `order`. This is the seam that hands real `Actor`s to `write_actor_tree`, whose
  `dump_actor_body` then strips identity tokens (so the stored `actor.t3d` matches the trunk's).
- `_is_old_format` is **not** a separate helper — the precedence lives inline in `read_prefab`
  (new-dir-wins: old only when `dest` is not a dir AND `<name>.t3d` is a file).
- `_read_old_prefab(root, name) -> (full, order, packages, meta)` — the ONLY old-format code: parse
  the `Begin Map` blob `<name>.t3d` into a Level; read `<name>.json`; return `order = raw["order"]`,
  `packages = raw.get("packages", [])`, and `meta = {k:v for k,v in raw.items() if k not in
  ("order","packages")}` (the exact structural-key strip today's `read_prefab` does at
  `stashlib.py:136-142`, preserved so a migrated prefab's `meta.json` carries only `anchor`/`ts`).

Prefab adopts the **staging-swap** the stash already uses (today `write_prefab` overwrites in place),
so a per-actor rewrite never leaves ghost actor dirs and lands atomically. Because ranks are
**preserved** (below), an unchanged actor's `actor.t3d` + `order_value` are byte-identical rewrite to
rewrite, so git sees no spurious churn and the committed prefab stays merge-clean.

### Rank assignment for stash/prefab (`_ranks_for`)

Stash/prefab callers hand an **`order` list**, not per-actor `order_value`s. To keep committed
prefabs merge-clean, ranks must be **stable across rewrites**, not re-minted every save:

```python
def _ranks_for(order, prior):     # prior = {name: order_value} read from the existing tree ({} if fresh)
    ranks = {}
    for n in order:
        if n in prior:
            ranks[n] = prior[n]                            # SURVIVING actor keeps its order_value
        else:                                              # NEW actor: minted strictly after every
            ranks[n] = t3dtree.append_rank({**prior, **ranks})   # current + already-assigned rank
    return ranks
```

Fresh capture (`prior = {}`) therefore lays down ranks in capture order (equivalent to
`initial_ranks(len(order))`); a later `--target prefab/…` edit preserves every surviving actor's rank
and appends only the genuinely-new ones. (This mirrors `TrunkLevelSource.save`'s preserve-then-append
rule, so all three trees rank identically — required by §6's consistency test.) A tie in freshly
minted ranks is harmless (the `(order_value, name)` sort tiebreaks by name, per `decisions.md`
2026-07-05 15:11).

> **Note — the `order` list stays the public currency.** Stash/prefab callers and the
> `StashLevelSource`/`PrefabLevelSource` continue to speak a flat `order` list; `order_value`s are an
> **internal on-disk detail** derived on write and re-derived (sorted) on read. This keeps the
> `LevelSource.save(ranks=…)` CSG-override channel trunk-only exactly as today — the ordering verbs
> still reject a stash/prefab target, so no override ever reaches these wrappers.

---

## 2. How the per-tree EXTRAS coexist (`meta.json`, `packages`)

- **Both stash and prefab** now write `<tree>/packages` (newline list) and `<tree>/meta.json`
  (`json.dumps(sort_keys=True)`) as **siblings of `actors/`** via `write_sidecars`. The trunk writes
  neither (it has no siblings) — `read_actor_tree` never looks for them.
- **Prefab's single JSON is SPLIT.** Today `write_prefab` writes ONE `<name>.json =
  {"order":…, "packages":…, **meta}` and `read_prefab` carefully strips the structural keys back out
  (the "meta must not carry stale order/packages or a re-save clobbers the fresh ones" trap, guarded
  today at `stashlib.py:138-142` and pinned by `test_target_flag.py:186`). The new split **eliminates
  that trap entirely**: `order` is gone (it's the `order_value` sort), `packages` is its own sibling
  file, and `meta.json` holds ONLY the capture extras (`anchor`, `ts`). So `read_prefab` returns
  `meta` that is already free of structural keys with no filtering — the `{k:v for … if k not in
  ("order","packages")}` dance is deleted. Keep a regression that a save→edit→save cannot resurrect a
  dropped actor (the `test_target_flag.py` intent) against the new shape.
- **Preserve unchanged:** `stashlib.referenced_packages` (the texture-only `packages` set — brush
  poly texture-prefix, non-Engine), the capture **anchor** (`meta["anchor"]` = pre-shift bbox-min,
  written by capture, consumed by `stash apply`), `normalize_for_capture`, `with_folder` /
  `with_group`, `validate_member_name`, and the resolved-path **containment** check (moved to guard
  the prefab **dir**, §1).

---

## 3. Actor identity as a directory name — the quoting reconciliation

The flat stash encoded actor filenames with `tree_io.safe_name` (`urllib.parse.quote(..., safe="._-")`)
and un-quoted on read. The trunk instead makes the **dir name the identity verbatim** and *rejects* a
name that isn't a safe single segment (`_check_safe_segment`: non-empty, not `.`/`..`, no `/` or `\`).

**Reconciliation: DROP `safe_name`/urllib-quoting entirely; use the member name verbatim as the dir
name, guarded by the trunk's `check_safe_segment` (the ONE shared scheme).** Inventing a second
encoding would itself violate the one-format invariant. Justification that this is safe:

- UnrealEngine object names cannot contain `/`, `\`, or `.` (the package/subobject separators) or be
  empty, so a real captured actor name IS always a safe segment — the historical `safe_name` quoting
  was defensive against characters that the engine never produces. `Brush123`, `Light0`,
  `Torch_ab12cd` all pass `check_safe_segment` unchanged and were already passed **unchanged** by
  `safe_name` too (it only touches path-hostile chars).
- A name that somehow *isn't* a safe segment now **raises** at `write_actor_tree` (naming the value),
  identically for trunk, stash, and prefab — a single, consistent failure mode instead of a silent
  percent-encoding. Per the CLI convention "no Python exception reaches the user, errors name the
  offending value", the wrappers surface it as a clean exit-2 (`_dispatch_stash` capture already
  catches `ValueError` → `_SelectionExit`; add the same guard on the prefab/promote path).

**Mover canonicalization must move to CAPTURE (a real regression trap, do NOT silently drop it).**
Today the stash read path runs `tree_io._canonicalize_mover_blob`, which resets a Mover's active
`KeyNum` to 0 on read. The new read path (`load_actor_body` → `canonical_actor_t3d`) does NOT touch
`KeyNum`, and neither does capture's `normalize_actor`/`canonical_actor_t3d`. So an EXTERNAL mover
captured via `stash capture --from-t3d`/`--from-stdin` at `KeyNum=3` would be stored and read back
non-canonical — a behavior change. **Fix: canonicalize movers at capture** — `_capture_from_t3d`
(and any `--from-t3d`/`--from-stdin` ingest) runs `movers.canonicalize_mover` on each Mover actor
before the blob is stored, so the stored `actor.t3d` is already `KeyNum=0` (matching trunk semantics)
and the read path needs no mover special-casing. Capturing from the trunk needs no such step (trunk
actors are already canonical). Pin it with a regression: capture an external mover at `KeyNum!=0` →
the stored/read-back body is `KeyNum=0` (§6.2).

**External-capture round-trip is safe because capture normalizes.** The strip/inject byte round-trip
(`dump_actor_body`/`load_actor_body`) is pinned (2026-07-01) for trunk-shaped actors; `stash capture
--from-t3d` admits arbitrary external blobs, but capture already runs them through `_validate_ingest_actors`
+ `canonical_actor_t3d` (and now `canonicalize_mover`), so what reaches `write_actor_tree` is
canonical — the same input domain the strip/inject was pinned against. `dump_actor_body` neutralizes
the brush model-ref to the constant `Model` regardless of the input ref's shape, and re-derives it
from the dir name on read, so a non-`Model'MyLevel.X'` external brush ref cannot break the round-trip
(it is overwritten, not preserved — exactly as for the trunk). §6.2 adds an external-`--from-t3d`
round-trip case to pin this.

**Consequence — `tree_io.py` loses its last production callers.** `read_state_dir` was used only by
`stash_register` (removed here) and `test_apply.py`; `safe_name` only by `stash_register` (removed)
and a stale comment in `surface.py:30`. After this change `tree_io.py` has no production caller.
`_canonicalize_mover_blob` (its private mover helper) is still imported by
`uedcli/tests/test_movers.py` (`test_canonicalize_blob_only_touches_movers`) — so deleting the file
breaks that test. **Recommend: relocate the mover-blob canonicalizer to `movers.py`** (as a public
`canonicalize_mover_blob`, the natural home — capture will call the actor-level `canonicalize_mover`
anyway), re-point `test_movers.py`'s import there, then **delete `uedcli/tree_io.py`**, update/remove
`test_apply.py::test_read_state_dir_round_trips_…`, and drop the `surface.py:30` comment reference.
If deletion feels too aggressive for one PR, leave `tree_io.py` with a `# DEAD except the mover
helper` banner and remove in a follow-up noted in `board/inbox/`.

---

## 4. Folders

Covered as **Open sub-choice (2)** above. Design consequence: `write_actor_tree` already writes the
`folder` sidecar from `Actor.folder` and `read_actor_tree` already loads it, so the shared path
*supports* folders on all three trees with no extra code — BUT the **stash/prefab wrappers cannot
carry a folder through the blob-based `full_level` dict** (a T3D blob has no folder). Under the
recommended (2a), `_level_from_blobs` sets `folder=None`, so captured members write **no `folder`
file** — today's behavior, preserved. Therefore folder files are, in effect, **trunk-only** through
the current wrapper contract; a captured/prefab member never has one unless option (2b) (with its
signature change) is chosen. **This directly constrains the §6.1 consistency test** — see §6.1: the
byte-identity assertion covers `actor.t3d` + `order_value` for all three, and covers `folder` only
for a folder-LESS actor set (or the test must give the trunk arm a folder-less actor too), because a
foldered trunk actor cannot be reproduced folder-for-folder by the folderless stash/prefab wrappers.

---

## 5. Migration

Covered as **Open sub-choice (1)** (the headline). Stash is machine-local throwaway under the
gitignored `.uedcli/` — **no migration path needed**: a stale-format stash entry (flat
`actors/<name>.t3d` + `order` file) is simply regenerated. Add a **stale detector**
`_is_stale_flat_stash(dest)` = "`dest/actors/` contains loose `*.t3d` FILES" (the old flat form;
`read_actor_tree` only iterates sub-DIRs, so it would otherwise return an empty Level while
`packages`/`meta.json` still read non-empty — an inconsistent half-empty result). A stale entry is
treated as **fully absent**:

- `read_stash` returns `({}, [], [], {})` (all-empty, incl. packages/meta) — no half-empty footgun.
- **`exists()` returns `False` for a stale entry** (add the stale check alongside the `meta.json`
  probe). Without this, `--target stash/<stale>` and the lifecycle reads would see the surviving
  `meta.json`, report the stash as present, then silently edit/promote **zero** actors. Returning
  `False` makes them say a clean `stash not found` instead — the honest signal that it must be
  re-captured. (`drop` stays idempotent.)

This is throwaway state; no user-facing migration step and no read-time mutation of the store.
Prefab migration is the real path — see (1); recommendation **(A) auto-convert-on-read + optional
`prefab migrate`**.

---

## 6. Test strategy

New/updated tests (host-native `bin/test`):

1. **CONSISTENCY (the invariant's teeth) — `test_t3d_tree_consistency.py` (new).** Take one fixed
   actor set (≥2 actors incl. a brush and a point actor), **folder-less** (see §4 — the stash/prefab
   wrappers can't carry a folder through the blob dict, so a foldered actor can't be byte-matched
   across trees). Write it three ways — a trunk level (`trunk.write_level`), a stash (`write_stash`),
   a prefab (`write_prefab`) — in the SAME order. **Rank-seeding constraint (load-bearing):** seed the
   trunk arm's `ranks` with `initial_ranks(n)` over the same order the stash/prefab wrappers derive
   (`_ranks_for(order, {})`); both reduce to the identical monotonic `rank_between(prev, None)` chain,
   so the `order_value` files match — the test MUST use this seeding or it fails spuriously on ranks,
   not on a real divergence. Assert the three `actors/` subtrees are **byte-identical**: every
   `actors/<name>/actor.t3d` and `order_value` matches across all three, and **none** writes a
   `folder` file. Assert `packages`/`meta.json` exist beside `actors/` for stash/prefab and are
   **absent** for the trunk.
2. **Round-trip — stash & prefab** through the shared path: `write_* → read_* →` identical
   `(full, order, packages, meta)`; `order` reflects the `order_value` sort; `meta` round-trips the
   `anchor`/`ts` and carries NO structural keys. **Plus two capture-normalization pins (§3):** (i) an
   EXTERNAL mover captured at `KeyNum != 0` (via `--from-t3d`) is stored/read-back at `KeyNum = 0`
   (canonicalized at capture); (ii) an external `--from-t3d` non-canonical actor round-trips to its
   canonical stored form (the strip/inject domain).
3. **Rank stability / merge-cleanliness:** `write_prefab` a 3-actor set, `read_prefab`, edit one
   actor's body, `write_prefab` again → the two UNCHANGED actors' `order_value` files are
   byte-identical between the two writes (no re-mint churn); the edited actor's body changed. Add one
   new actor → it gets a rank appended after all existing, surviving ranks unchanged.
4. **Migration (option A) — `test_prefab_migration.py` (new).** Materialize an OLD-format prefab
   on disk (`<name>.t3d` `Begin Map` blob + `<name>.json`), `read_prefab` it → correct
   `(full, order, packages, meta)` (meta stripped of `order`/`packages`); then `write_prefab` (or
   `prefab migrate`) → new dir form present, old `<name>.t3d`/`<name>.json` **removed**; `list_prefabs`
   returns the name across the transition (before AND after) and never emits a bogus inner
   `…/actors/…` entry. **New-dir-wins crash test:** with BOTH `<name>.t3d` (stale) and `<name>/`
   (new) present, `read_prefab` reads the NEW dir and ignores the stale file; the next `write_prefab`
   removes the stale file. Nested-name prefab (`hangar/archway`) migrates and lists correctly.
5. **Folder / order_value preservation:** a captured member has `folder = None` (no `folder` file);
   `apply --folder X` stamps `X` on the placed trunk actor (existing `test_folders`/stash-apply
   behavior still green).
6. **Extras beside the tree:** `packages` + `meta.json` are siblings of `actors/` (not inside it);
   `exists`/`list_stashes`/`list_prefabs` key on `meta.json` and see nested names; an emptied-to-zero
   stash still `exists`.
7. **Safety / naming:** an unsafe member name raises a clean, value-naming error (no percent-encoded
   dir); `validate_member_name` + the prefab dir-containment check still reject `../escape`; corrupt
   `meta.json` → clean exit-2 via the `LevelSource` load (existing `test_target_flag`/`test_stash_dispatch`
   coverage kept green against the new shape).

Update existing tests that assert the OLD on-disk shape: `test_stash_register.py`,
`test_stashlib.py`, `test_stash_dispatch.py`, `test_target_flag.py` (the `read_prefab` meta-filter
test → re-target to the split shape), and `test_apply.py` (the `read_state_dir` round-trip → remove
with `tree_io`). Keep the pinned `2026-07-01` git-merge fact intact (canonical emit is load-bearing).

---

## 7. Blast radius + docs to update on build

**Production code (≈4 files changed, 1 new, 1 deleted):**

- **`uedcli/t3dtree.py`** — NEW: the shared module (per-actor tree I/O + rank algebra + body
  strip/inject + `check_safe_segment` + `write_sidecars`/`read_sidecars`), moved from `trunk.py`.
- **`uedcli/trunk.py`** — becomes thin re-exports of the moved functions; `read_level`/`write_level`
  names preserved so its ~20 caller/test sites don't churn.
- **`uedcli/stash_register.py`** — `write_stash`/`read_stash` rewritten as wrappers over
  `t3dtree`; drop `from .tree_io import read_state_dir, safe_name`; `exists`/`list`/`drop` unchanged.
- **`uedcli/stashlib.py`** — `write_prefab`/`read_prefab`/`list_prefabs` rewritten (per-actor tree +
  split siblings + old-format read shim + dir-containment guard); `referenced_packages`,
  `normalize_for_capture`, `with_folder`/`with_group`, `validate_member_name`, `translate`,
  `format_summary` UNCHANGED. Add `prefab migrate` support if option B is chosen.
- **`uedcli/movers.py`** — gains a public `canonicalize_mover_blob` (relocated from
  `tree_io._canonicalize_mover_blob`), the new home for the mover-blob helper `test_movers.py`
  imports (§3).
- **`uedcli/tree_io.py`** — DELETE (no production caller after this change); or banner + follow-up
  (§3). Its mover helper moves to `movers.py` FIRST so `test_movers.py` doesn't break.
- **`uedcli/dispatch.py`** — mostly unchanged because the wrapper signatures are preserved
  (`full_level`/`order`/`packages`/`meta` in, `(full, order, packages, meta)` out). Verify/adjust:
  `_dispatch_stash` capture (`write_stash`) — **now canonicalizes movers on the `--from-t3d`/
  `--from-stdin` ingest** (`_capture_from_t3d`, §3); `_promote_stash` (its `meta` = `{anchor, ts}`
  flows into the split `meta.json` — assert it carries no `order`/`packages`); `_apply_set`;
  `StashLevelSource.save`/`PrefabLevelSource.save`; `_read_prefab_or_exit`; add the `prefab migrate`
  verb wiring + argparse entry if option B lands. **Update the `PrefabLevelSource` docstring**
  (`dispatch.py:1119-1123`) — it references "the tracked `.t3d` + JSON sidecar" and the meta-strip,
  both obsolete under the per-actor tree + split siblings. `surface.py:30` comment reference to
  `tree_io.safe_name` dropped.

**Tests touched:** `test_stash_register.py`, `test_stashlib.py`, `test_stash_dispatch.py`,
`test_target_flag.py` (its `read_prefab` meta-filter test → re-target to the split shape),
`test_apply.py` (the `read_state_dir` route → remove with `tree_io`), `test_movers.py` (re-point the
`_canonicalize_mover_blob` import to `movers.canonicalize_mover_blob`), and
`test_integration_stash_intersect.py` (round-trips `write_stash`/`read_stash` — signatures preserved,
so verify-green rather than rewrite). `test_generators.py` mocks `read_stash` — return contract
unchanged, verified compatible. **New:** `test_t3d_tree_consistency.py`, `test_prefab_migration.py`.
(~7 existing test files touched, 2 new.)

**Docs to update (per the tool's "no doc left stale" rule):**

- **`dev/docs/architecture.md`** — the "Stash / prefab" section (lines ~254-279: stash is no longer
  the flat `read_state_dir` tree; prefab is no longer `.t3d`+`.json` — both are the per-actor tree +
  siblings), the `LevelSource` section (lines ~182-214: the "flat `order` list / `_ranks` empty"
  wording; the `read_prefab` meta-strip note is gone), and the module map (lines ~116-117:
  `tree_io.py`/`read_state_dir`/`safe_name` removed; add `t3dtree.py`).
- **`docs/usage.md`** — the prefab "a `.t3d` + `.json` sidecar" description (lines ~373-374) and the
  stash `.uedcli/stash/<id>/` shape (line ~372) → the per-actor tree; add `prefab migrate` to the
  verb list if option B lands.
- **`dev/docs/decisions.md`** — append a short entry recording the resolved sub-choices (migration
  option, folder-on-capture) once Andrzej confirms. **(Not written by this spec — decisions are
  Andrzej's to record.)**
- **`dev/docs/board/`** — cross off / add TODOs per the flow; note the `tree_io.py` deletion (or its
  deferred follow-up) if not done in the same PR.
- This spec file is ephemeral — fold the durable outcome (the shared module, the sibling split, the
  dropped quoting) into `architecture.md`, then it may be deleted.

**Ordering / invariants preserved:** per-actor atomic writes (tmp + `os.replace`), the whole-tree
staging swap for stash/prefab (ghost-free rewrite), canonical emit (the load-bearing merge fact),
`meta.json` as the stash/prefab existence marker, nested names, the never-overwrite-without-force
guard, and path-containment. Nothing about the trunk's own read/write behavior changes — the code
merely moves and gains two more callers.
