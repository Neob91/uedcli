# `--target` — generic content-verb targeting (level / stash / prefab)

*Ephemeral design scratch. Decisions land in [`decisions.md`](../decisions.md) (2026-07-12 03:06 UTC);
once built, fold the durable parts into `architecture.md`. Delete this when the work lands.*

> **BUILT 2026-07-12.** Implemented per this spec (incl. all [spec-review HIGH] fixes). Durable
> design folded into `architecture.md` → "The `LevelSource` seam and `--target`"; usage note in
> `docs/usage.md`. Safe to delete this scratch.

## Goal

Let the shared **content verbs** operate on any of the three T3D actor-set "boxes" — the selected
level (today's behavior), a **stash**, or a **prefab** — selected by a single flag:

```
--target <kind>/<name>        # kind ∈ {level, stash, prefab}; default: level/<current level>
```

**Driving use case: prefab _template_ editing.** Fixing a library component today is a 4-step
roundtrip (`prefab X apply` → edit in the level → `stash … capture` → `promote --force`). With
`--target` it's one command:

```
uedcli brush poly set Panel:2 --texture DeusExDeco.Rivet --target prefab/door
uedcli actor move Panel --by 0,0,16 --target prefab/door
```

Level and stash targeting fall out of the same mechanism at ~no extra cost; explicit
`--target level/<other>` (edit a level without `level select`) is a free bonus.

## Why this is small: the `LevelSource` seam

Every content verb already does only this about *where* the data lives:

```
src = _resolve_level_source(args)   # the ONE place that picks the box
level = src.load(); … transform …; src.save(verb=…, level=level, touched=…)
```

So the whole feature is: **two new `LevelSource` classes + a parse branch in
`_resolve_level_source`.** Verbs stay source-agnostic — zero per-verb logic changes; the only
per-verb edit is *adding the flag* (one shared helper).

## Grammar

- **Flag:** `--target KIND/NAME`, metavar `KIND/NAME`, added to every shared content verb via one
  helper `_target_flag(parser)` (mirrors the existing `_apply_flags`/`_preview_opts` helpers).
- **Parse:** split on the **first** `/`. The prefix must be one of `{level, stash, prefab}`
  (fixed set → unambiguous); the remainder is the NAME, which may itself be nested
  (`--target stash/hangar/archway` → kind `stash`, name `hangar/archway`).
- **Default:** omitted ⇒ `level/<current selected level>` — i.e. exactly today's behavior. The safe
  durable default; scratch/library must be named explicitly (this is what dissolves the
  "accidentally edited a stash" footgun).
- **Errors (all clean exit 2, never a traceback):**
  - malformed value (no `/`, empty name) → `--target must be KIND/NAME (KIND ∈ level|stash|prefab)`
  - unknown kind → names the offending kind
  - target doesn't exist → reuse the not-found guards: `stash not found: '…'` /
    `prefab not found: '…'` / `level not found: '…'`

## Which verbs get `--target`

**Yes — the shared content verbs that either MUTATE or have no per-kind equivalent:**
`actor add/delete/move/prop/rotate/find/get`, `brush clip/vertex/poly`, `mover key add/move/rotate/remove/list`.

**No — and deliberately (spec-review resolution):**
- **`actor show` / `brush preview`** — a **per-kind verb already exists** (`stash show`/`prefab show`,
  `stash preview`/`prefab preview`), so `--target` there would be pure two-ways-to-do-it redundancy.
  Keep the dedicated verbs; don't add `--target` to `show`/`preview`. (`find`/`get` DO get it — there
  is no `stash find`/`prefab get`, so they're genuinely new capability.)
- **Generators** (`actor build`, `brush build`) — they write T3D to stdout, targeting nothing.
- **Level-lifecycle** (`level materialize/preview/select/status/doctor`) — inherently level-scoped
  (you don't materialize a stash). They keep resolving the selected level with no `--target`.
- **Container-lifecycle** (`stash capture/apply/promote/drop/intersect/deintersect`,
  `prefab apply/drop`) — kind-specific by nature; unchanged.

**Help string** (the single `_target_flag` text — the only place a reader learns the set + default):
`"operate on this box instead of the selected level: KIND/NAME where KIND is level|stash|prefab and
NAME is the level/stash/prefab name (may be nested, e.g. stash/hangar/arch). Default: the selected
level."`

**Reverse discoverability** (spec-review note): `prefab -h`/`stash -h` won't reveal that content
verbs can now target them. Close it cheaply — a line in the `prefab`/`stash` **group** help pointing
at `--target`, and a `usage.md` cross-link.

**`brush poly set` name clash** (spec-review): `poly set` already has a positional `dest="targets"`
(the `BRUSH:SELECTOR` surfaces). No argparse collision with `--target` (dest `target`), but two
senses of "target" on one verb is confusing. Rename that positional's INTERNALS to a
surface/selector word (`dest`, `parse_poly_target`→`parse_poly_selector`, the "poly target must be…"
error text) — metavar stays `BRUSH:SELECTOR`, so it's an internal + error-message cleanup that frees
"target" for the flag. Bundled into this change.

## Prerequisite fix (stashlib) — the prefab `meta` clobber [spec-review HIGH]

**This must land before/with the sources or `actor add/delete --target prefab/…` corrupts the
prefab.** `write_prefab` writes ONE sidecar `json.dumps({"order": order, "packages": packages,
**meta})` — `**meta` spreads LAST — and `read_prefab` returns `meta = the WHOLE sidecar dict`
(including `order`/`packages`). So re-saving with the read-back `meta` lets the STALE order/packages
override the fresh ones → a newly-added actor is dropped and a deleted one resurrected on the next
read. (Latent today because nothing re-saves a prefab; `PrefabLevelSource.save` is the first.)

**Fix:** make `read_prefab` return `meta` **without** the structural keys —
`meta = {k: v for k, v in raw.items() if k not in ("order", "packages")}` — so `write_prefab`'s
`**meta` can't clobber. (Verified no caller reads `meta["order"]`/`meta["packages"]` — they use the
separate tuple elements.) Add a round-trip **add-then-read** prefab test that would have caught this.

## The three sources

`TrunkLevelSource` (exists) already implements `load()`/`save(verb,args,level,touched)`. The two new
ones mirror it (~15 lines each):

```python
class StashLevelSource:      # stash/<id>, via FileStashRegister
    def load(self):
        blobs, order, self._pkgs, self._meta = self.reg.read_stash(self.id)
        lvl = parse_t3d("Begin Map\n" + "\n".join(blobs[n] for n in order if n in blobs) + "\nEnd Map\n")
        lvl.order = [n for n in order if n in blobs]; return lvl     # guard: no bare KeyError [SR-#3]
    def save(self, *, verb, args, level, touched):
        full = {n: canonical_actor_t3d(level.actors[n]) for n in level.order}
        self.reg.write_stash(self.id, full_level=full, order=level.order,
                             packages=sorted(stashlib.referenced_packages(level.actors.values())),
                             meta=self._meta, force=True)

class PrefabLevelSource:     # prefab/<name>, via stashlib.read_prefab/write_prefab (meta now clean)
    # identical shape; save passes the cleaned self._meta back (no order/packages inside it)
```

- **`if n in blobs` guard** on the `order` join (both sources) — a stored `order` naming a
  missing blob must not raise a bare `KeyError` to the user (every other call site guards this).
- `_ranks = {}` — stash/prefab use a flat `order` list, no `order_value` sidecars. Content verbs
  don't read `_ranks` (only `level status`/`doctor` do, and those are level-only), so `{}` is safe.
  *(Confirmed by spec review: no content verb reaches past the `src` seam into `trunk_dir`/`_ranks`.)*
- **Save recomputes `packages`** from the edited actors (`referenced_packages`) so a
  `poly set --texture NewPkg.X` edit updates the stored dep set; `meta`/anchor preserved. **Limitation
  (state as non-goal):** `referenced_packages` is **texture-only** (class/mesh/sound packages aren't
  string-derivable from T3D), so a hand-added non-texture package in a sidecar is dropped on save —
  NOT a regression (capture/promote also stored texture-only, and the field is vestigial: materialize
  derives the real load set from the composed search path, not the sidecar).
- `write_stash`/`write_prefab` with `force=True` for in-place overwrite (both swap atomically:
  staging dir + `os.replace`, so a crash never leaves a half-written box).

## Dispatch change

`_resolve_level_source(args)` gains a front branch:

```python
tgt = getattr(args, "target", None)
if tgt:
    kind, sep, name = tgt.partition("/")         # split on FIRST '/'
    if not sep or kind not in ("level","stash","prefab") or not name:
        raise _SelectionExit("--target must be KIND/NAME (KIND ∈ level|stash|prefab), got …")
    stashlib.validate_member_name(name)          # [SR-#2] MANDATORY: no path traversal on read OR write
    project = _resolve_project(args)             # all three live under the project
    if kind == "stash":  <not-found guard>; return StashLevelSource(reg, name)
    if kind == "prefab": <not-found guard>; return PrefabLevelSource(root, name)
    # kind == "level": named level's trunk; validate the maps/<name>/ dir exists (else clean "not found")
    return TrunkLevelSource(maps_dir / name)
# else: today's path — the selected level
```

- **[spec-review HIGH — path traversal]** `read_stash`/`read_level` do **not** validate the
  top-level name (only `write_stash` does; the trunk guards actor *segments*, not the level dir). So
  `--target stash/../../x` would escape on BOTH load and the subsequent save. `validate_member_name`
  (rejects `..`, absolute, backslash, bad chars) MUST run in the front branch **before** any source
  is constructed — matching the existing `_dispatch_prefab` discipline. A `ValueError` from it
  surfaces as clean exit 2.
- **Grammar vs existence:** the grammar check (`sep`/kind/name) could alternatively be an argparse
  `type=` so a malformed `--target` is attributed to the arg and fails before project resolution;
  existence checks must stay here (they need the project). Either is fine — dispatch-time is simplest.
- Prefab library root resolves the usual way (`prefab_library_root()` + `UEDCLI_PREFAB_DIR`); content
  verbs do **not** grow a `--prefab-dir` flag. **Asymmetry to accept:** a prefab in a NON-default
  library is editable via `prefab show --prefab-dir …` but not via `--target` (env/default root only).
  Acceptable edge; stated so it's not a silent hole.

## Non-goals (state them so they aren't assumed)

- **No instance/placement refresh.** Editing a prefab changes the *template* for future `apply`s; it
  does NOT update copies already applied into levels (apply = copy with fresh names, no back-link).
  "Update every placed door" is a separate, much larger feature and is out of scope.
- **No new lifecycle verbs.** capture/apply/promote/materialize stay as they are.
- **No `stash`/`prefab` grammar migration** — lifecycle stays verb-first (`prefab show door`,
  `stash apply bay`). `--target` only rides the content verbs. Fully additive.
- **No cross-target moves** (e.g. "move actors from a stash into the level" in one verb) — that's
  what `stash apply` already does.
- **Locking:** in-place edits rely on the atomic swap (last-writer-wins on a concurrent same-box
  edit — no corruption, but no merge). Acceptable for v1; note it.

## Test plan (offline, seam-mocked)

- Parse: valid `level|stash|prefab/name`, nested name, malformed (no `/`), unknown kind → messages.
- `_resolve_level_source` returns the right source per kind; default (no flag) = selected level.
- Round-trip each source: `load()` then `save()` writes the box back (mock the register/library);
  a `--texture` edit updates the stored `packages`.
- Not-found per kind → clean exit 2.
- One end-to-end per box via a real tmp project: `actor move … --target prefab/door` mutates the
  on-disk prefab sidecar; `--target stash/bay` mutates the stash; `--target level/other` mutates a
  non-selected level's trunk.
- **[SR-#1 regression] prefab add-then-read round-trip:** `actor add --target prefab/door`, then
  re-read the prefab — the added actor SURVIVES and the sidecar `order`/`packages` are the fresh
  ones (guards the `meta` clobber). Same for `actor delete` (the deleted actor stays gone).
- **[SR-#2 regression] path traversal:** `--target stash/../../x` / `level/../../x` / `prefab/../x`
  → clean exit 2, and NOTHING is read or written outside the box root (assert no escape file).
- **[SR-#3] a stored `order` naming a missing blob → no `KeyError`** (clean load, missing name skipped).
- Discoverability: `--target` present on a representative content verb; absent on `brush build`,
  `level materialize`, `actor show`, `brush preview`.

## Decisions

Recorded in [`decisions.md`](../decisions.md) **2026-07-12 03:06 UTC** — the flag name (`--target`
over `--in`/`--scope`/`--t3d-tree`/`--store`, with rationale), the `KIND/NAME` split-on-first-`/`
grammar, default `level/<current>`, the verb scope, save-side package recompute, and the non-goals.
