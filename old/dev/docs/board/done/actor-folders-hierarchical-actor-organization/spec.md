# Actor folders — hierarchical organization (the "groups overhaul")

**Status:** spec (ephemeral — fold into `architecture.md` + `unrealed/t3d.md` on build).
**Decisions ledger:** [`decisions.md` 2026-07-18 12:14 UTC](../../../decisions.md). Every load-bearing
choice below is Andrzej's, recorded from the speccing Q&A; this spec compiles them.
**Supersedes** the inbox item "Hierarchical (nested) groups + group-path queries in `actor find`"
(Andrzej, 2026-07-12).
**Pairs with** (separate, still-inbox spec) "Name-taking verbs accept actor names from STDIN (`-`)"
— `actor folder set -` and `actor find --folder … | …` compose fully once that lands.

---

## 1. Motivation & the concept

A big build needs to be organized as a **tree**, not a flat namespace: `castle.tower.roof`,
`castle.moat.water`, so logical subsets are addressable ("retexture every `**.roof`", "list
`castle.moat.**`"). Today the only cohesion mechanism is the flat T3D `Group=` property — a plain,
comma-separated membership string with exact-per-member matching and no hierarchy
(`query._group_matches`).

This spec introduces a **folder**: a per-actor, hierarchical, dotted organizational path that is
**entirely uedcli-side** — it lives in the trunk, never in the built map, and is a *separate
dimension* from the T3D `Group` property.

### Naming: why `folder`, not `group`
The word "group" is already overloaded three ways in the codebase — the T3D `Group=` actor prop,
the texture-package middle segment (`Package.Group.Name`), and the property-browser `var(Group)`
category. The new concept is named **`folder`** to avoid all three collisions, and because it is
never emitted to the editor there is no clash with UnrealEd's native `Group=`.

### Relationship to the T3D `Group` property — they are INDEPENDENT
The T3D `Group=` property is **retained unchanged**: parsed, stored in `Actor.props`, and emitted
(always re-quoted) exactly as today (`model.py:138`, `emit.py:66-68,127-128`). A folder is **not**
absorbed from, derived from, or written into `Group`. An actor can carry both a `Group=` prop and a
folder; they never interact. (Decision 2: "Group not used for folder, but retained as a T3D prop
unchanged.")

---

## 2. Storage model — a per-actor sidecar

A folder is a **typed field on the model** and a **per-actor sidecar file in the trunk**, beside
`order_value`:

```
maps/<level>/actors/<name>/
    actor.t3d       # unchanged (folder is NOT in here)
    order_value     # unchanged
    folder          # NEW — one line: the dotted path, e.g. "castle.tower.roof\n"
```

- **Model:** `Actor.folder: str | None` — a typed field like `location`/`name`, **not** a `props`
  entry. `None` = ungrouped (no folder file).
- **Why a sidecar, not a T3D prop** (Decision, Andrzej): "I do not want the folder to land under the
  Group prop. It should be non-T3D, next to the order value file. T3D Group can't handle long
  values." Deep dotted paths would overflow UnrealEd's FName length limit on `Group=`; the sidecar
  sidesteps that entirely. Like the rest of the per-actor trunk layout, disjoint edits compose under
  `git merge` (a folder change on actor A and a body change on actor B never touch the same file);
  two divergent edits to the *same* actor's folder conflict exactly like divergent body edits (one
  line, both sides changed) — the layout removes cross-actor false conflicts, not same-line ones.
- **Single path per actor** (Decision): each actor belongs to exactly one folder path. No
  multi-membership (drops today's comma-list capability — cross-cutting selection uses `--class` /
  `--prop`, not folders). *Rejected:* keeping comma multi-membership.

### Trunk I/O (touchpoints in `trunk.py`)
- `read_level_with_bodies` / `read_level`: read `folder` (strip; absent/empty → `None`) into
  `Actor.folder`, alongside the `order_value` read (`trunk.py:216-217`).
- `write_level`: write the `folder` file when `actor.folder` is set; when it is `None`, **remove any
  existing `folder` file** (so `actor folder unset` actually clears it). **Write it atomically via
  `tmp + os.replace`, exactly like `actor.t3d`** (`trunk.py:164-169`) — loads take no flock, so a
  plain `write_text` would let a lock-free reader mid-write see a truncated first line and misreport
  the actor as ungrouped, skewing a concurrent `actor find --folder`. Ordering is not
  identity-critical (unlike `order_value`→`actor.t3d`, the admission gate stays "`actor.t3d`
  exists"), so the folder may land last; but each individual folder write/removal is atomic.
- **Delta-write diff must include the folder — in BOTH directions.** `TrunkLevelSource.save` decides
  its changed set (`only`) by content-diffing `actor.t3d` body + rank against the load snapshot
  (`dispatch.py:942`, `read_level_with_bodies`, `architecture.md` write-pattern step 4). A
  **folder-only** change leaves body+rank identical, so the diff **must also compare the folder** or
  the write is silently dropped. This is symmetric: it must fire on **any** load-vs-current folder
  delta, explicitly **including `"x"`→`None` (unset)** — else `actor folder unset` no-ops exactly
  like the set trap. Concretely: extend `read_level_with_bodies` to return a name→folder map as a
  4th tuple element (rippling to `read_level` at `trunk.py:191` and `TrunkLevelSource.load` at
  `dispatch.py:914`, whose `_loaded_bodies` baseline gains a loaded-folders map), and add folder to
  the per-actor change test. *(This is the one non-obvious implementation trap — call it out in the
  plan.)*

### Not part of the canonical level hash
`normalize.canonical_level_hash` folds in the actor bodies + `level.order`. A folder is in neither
(separate sidecar, not emitted to the map), so it is **naturally excluded** — the materialized `.dx`
is byte-identical regardless of foldering. This is correct: folders are authoring metadata with zero
build effect (same class as lighting/BSP being build output, `direction.md`). Confirm no hash change
is needed; add a regression asserting two trunks differing only in folders hash equal.

---

## 3. Path grammar & matching semantics

### Stored path (what `actor folder set` / `actor add --folder` accept)
- Non-empty; segments separated by `.`; **every segment non-empty** (reject `a..b`, leading/trailing
  `.`).
- Per-segment allowed characters: `[A-Za-z0-9_+-]` (conservative — folders are never emitted to the
  editor so there's no FName char constraint, but a stored path must not contain the pattern
  metacharacters or separators that would make queries ambiguous). **Reject** `*`, `,`, whitespace,
  `/`, `\`, and `.` inside a segment. *(Char set is a review point — see §8 R2.)*
- **Case:** stored **as authored** (case preserved for display); **matched case-insensitively**
  (FName-consistent, mirrors today's `casefold` group match and `architecture.md`'s "name/class/group
  matching is case-insensitive").

### Query pattern (what `actor find --folder` accepts) — the globstar rule
Andrzej adopted the standard globstar grammar. `*` is the **only** wildcard; `**` (two adjacent
stars filling a whole segment) is the only multi-segment token. **`?`, `[`, `]` are NOT wildcards
here** — a query pattern is validated against the same per-segment charset as a stored path
(`[A-Za-z0-9_+-]`) *plus* the `*` token, and any other metacharacter is rejected (exit 2). This is
deliberate: it stops an `fnmatch`-based implementation from silently leaking `?`/`[...]` semantics
the grammar never sanctions.

| Token | Meaning |
|---|---|
| a **wildcard-free** pattern `X` | `X` **and its whole subtree** (X, and any path with prefix `X.`) |
| `*` | exactly **one** path segment (non-empty) |
| `**` | **any depth** — zero or more segments |

**Wildcard-detection predicate:** a pattern is "wildcard-free" iff it contains no `*`. That single
test drives the subtree-vs-glob switch below, so it must be exact.

**Matching algorithm (normative — the table is illustrative, THIS is the definition):**
1. Split both the pattern and the actor's folder on `.` into segment lists (matching is
   **case-insensitive** — casefold both first).
2. **If the pattern is wildcard-free:** it matches iff the folder equals the pattern **or** the
   folder is a descendant — i.e. `folder == pattern` or `folder` starts with `pattern + "."`.
   (Segment-boundary prefix, so `cast` does NOT match `castle`.)
3. **If the pattern contains any `*`:** translate to an anchored regex over the joined path and
   match the **whole** folder string (no implicit subtree extension):
   - a `*` segment → `[^.]+` (one non-empty segment);
   - a `**` segment → collapses with an adjacent separator to `(?:[^.]+(?:\.[^.]+)*)?` **and** the
     neighbouring `.` is absorbed, so `X.**` → `^X(?:\..*)?$` (matches `X` itself and any descendant)
     and `**.roof` → `^(?:.*\.)?roof$` (matches top-level `roof` and any `*.roof`). This
     separator-absorption is the boundary rule real globstar implementations differ on — it is
     **mandatory** here and the `**`-matches-zero cases in the table below depend on it.
   - a literal segment → the escaped segment text.
4. `folder = None` (ungrouped) matches **no** `--folder` pattern (it is the empty path; mirrors
   `_group_matches` returning `False` for a groupless actor). Select the ungrouped set with
   **`actor find --no-folder`** (see §4), not a pattern.

Worked examples (folder `castle.tower.roof` present):

| Pattern | Matches |
|---|---|
| `castle` | `castle`, `castle.tower`, `castle.tower.roof`, `castle.moat` (whole subtree — bare = subtree) |
| `castle.*` | direct children of `castle` **only** (`castle.tower`, `castle.moat`) — **not** `castle.tower.roof` |
| `castle.**` | the whole `castle` subtree (`**` absorbs zero+, so equivalent to bare `castle`) |
| `**.roof` | a `roof` at **any** depth, including a top-level `roof` |
| `*.roof` | a `roof` at depth **exactly 2** (`castle.roof`, not `castle.tower.roof`) |
| `*.**.roof` | a `roof` at depth **≥ 2** (superset of `*.roof`) — legal but esoteric |

- **No triple-star.** "One or more segments" is already expressible and `***` is not a thing in any
  standard glob (Andrzej: leave it out).
- Repeated `--folder` flags **OR** (match any pattern), mirroring today's `--group`.

> **⚠ The main UX risk — the subtree/glob asymmetry (document loudly in `--folder` help).** A
> *wildcard-free* pattern selects a whole subtree, but *any* wildcarded pattern is a pure glob with
> **no** subtree extension. Two consequences to surface to users:
> - **Non-compositional `**.roof`:** `**.roof` matches the `roof` **nodes only**, NOT what's under
>   them. "Every roof at any depth *and everything inside each*" needs two patterns:
>   `--folder '**.roof' --folder '**.roof.**'`.
> - **Bare over-selects the node case:** an actor placed directly "in `castle`" (folder exactly
>   `castle`) is matched by `--folder castle` — but so is its whole subtree, and there is no
>   short form for "the `castle` node only" (exact-single-node is deferred, §8 R3). This is the
>   common "I meant just this folder" foot-gun; the `--folder` help must say bare = subtree.
> *(Andrzej chose bare = subtree AND globstar explicitly; this is a documentation duty, not a
> reopened decision. The uniform alternative — bare = exact, require a trailing `.**` for the
> subtree — was considered and not chosen.)*

### Exact-single-node match is DEFERRED
Because a wildcard-free pattern = subtree, there is no form for "exactly this folder, excluding
descendants." Earlier that role was to be `--prop Group=…`, but folders are not props, so that path
is gone. Exact-only is a niche need; **defer** it (a trivial later add, e.g. `--folder-exact` or an
`=path` sigil). Filed to inbox. *(Review point §8 R3.)*

---

## 4. CLI surface

### `actor folder` — the management verb (`set|unset|get`, in the spirit of `actor prop`)
Since a folder is a sidecar (not a T3D prop), `actor prop --set Group=` does **not** set it; a
dedicated verb is required. It follows `actor prop`'s **set/unset/get** shape, but the argument
grammar deliberately **differs** — `actor prop set <actor> KEY=VALUE…` takes a **single** actor
then value tokens (`cli.py:230`), whereas folder is one path assigned to **many** actors, so the path
goes on a **flag**, not a trailing positional:

- **`actor folder set --to <path> <names…>`** — assign `<path>` to each named actor. **Path on the
  `--to` flag, names variadic** — this avoids the two-greedy-positionals ambiguity of
  `set <names…> <path>` (which token is the path?) and, critically, **composes with the paired
  STDIN-`-` feature**: `actor find --group wip | actor folder set --to act2.wip -`. Validate-all
  (names resolve, path grammar) **before any write**; all sidecars land or none do.
- **`actor folder unset <names…>`** — clear the folder (remove the sidecar file).
- **`actor folder get <names…>`** — print each actor's folder path, one line per actor in argument
  order; ungrouped prints an explicit **`(none)`** sentinel (chosen now, not deferred — a blank line
  is ambiguous; see §8 R4-resolved).
- **Trunk-only target.** A folder lives only in the per-actor trunk dir; the stash/prefab boxes
  serialize via `canonical_actor_t3d` (T3D only — `dispatch.py:980-1015`) and have no per-actor
  sidecar slot. So `actor folder set/unset/get` (and `actor add --folder`, and find's
  `--folder`/`--no-folder`) **reject `--target stash|prefab` with a clear exit-2 error** ("folders
  apply only to a level target"), rather than silently writing a sidecar that's dropped on save or
  querying a dimension that's always `None`. *(Resolves review B3/S5.)*
- v1 is **assign-only**: no whole-subtree rename/move verb (`folder rename` is filed to inbox).

### `actor add --folder <path>` — set folder at creation
`--folder` lives on **`actor add`**, the verb that writes the trunk — **not** on the generators
(Decision). This honors the generator pattern ("generators write to neither the trunk nor the stash;
the write into the trunk lives *exclusively* at `actor add`", `direction.md`). All actors added by
the invocation get `<path>`.

```
brush build cube --at 0,0,0 | actor add - --folder castle.wall.north
actor add prefab.t3d --folder castle.props
```

- `brush build` / `actor build` get **no** `--folder` flag (superseding the pre-sidecar item text —
  they stay pure T3D producers).
- The **existing** `brush build --group` flag is unaffected (it writes a T3D `Group=` prop, a
  different thing). *(Whether to keep it is orthogonal; left as-is.)*
- **`actor add` also PARSES a `// uedcli-folder: <path>` carrier** out of the incoming T3D (the
  `actor show` interchange form, below) into the sidecar, then strips it from the stored body.
  Precedence: an explicit `--folder` **overrides** any carrier in the stream; absent `--folder`, the
  carrier (if present) sets the folder; absent both, the actor is ungrouped. Generator output has no
  carrier, so `brush build | actor add - --folder X` is unaffected. *(This is the round-trip half of
  the `actor show` design below — the parser must recognize the bare `//` line; other `//` comments
  are ignored as ordinary comments.)*

### `actor find --folder <pattern>` / `--no-folder` — the query
`list_actors` gains a `folders` matcher (globstar, §3) over `Actor.folder`, wired like today's
`groups` param (`query.py:163,192`; the `actor find` dispatch that passes it ≈ `dispatch.py:2007-2015`;
`cli.py:145-149` clone for `--folder`). AND across dimensions, OR within the repeated flag.
- **`--no-folder`** selects the **ungrouped** set (actors with `folder is None`) — the only way to
  query them, since `None` matches no `--folder` pattern (§3). `--folder` and `--no-folder` are
  mutually exclusive.
- The existing **`actor find --group`** flag (T3D `Group` prop membership) is **retained** — and
  single-path-per-actor **forces** keeping it, not merely "for now": folders can't express arbitrary
  cross-cutting tags (`wip`, `act2`, `reviewed`) the way `Group`'s comma-list can, and `--class`/
  `--prop` are fixed dimensions, so `--group` is the multi-tag safety valve. **Do not retire it while
  folder is single-path.** *(Resolves review R1/S2 — §8 R1 is now decided KEEP.)*

### `actor show` includes the folder as a `// uedcli-folder:` comment (R6 RESOLVED by the spike)
The interchange encoding of a folder is a **bare `// uedcli-folder: <path>` T3D comment line** placed
inside the actor block (omitted when the actor has no folder). This **reconciles the two goals
Andrzej raised** — "`actor show | actor add -` should retain the folder" AND "`actor show` should
expose UnrealEd-compatible T3D" — in **one default output**, because the spike proved UnrealEd's T3D
importer **silently strips `//` line-comments** (`Core.dll ParseLine`, gated `Exact==0` + not-in-quotes;
static-RE **and** live `MAP IMPORTADD` confirmed, `spikes/2026-07-18-t3d-comment-tolerance/`,
`unrealed/t3d.md`):
- `actor show A` → an importable T3D block carrying `// uedcli-folder: castle.tower.roof`.
- `actor show A | actor add -` → uedcli's own parser reads the comment back into the sidecar
  (**folder round-trips**).
- The same text pasted/imported into UnrealEd → the `//` line is silently dropped, no warning, no
  crash (**UnrealEd-compatible**).

So the DEFAULT `actor show` output is **both** folder-carrying and editor-importable — no flag needed
for the pipe. **`--t3d-only`** remains, now meaning "suppress the comment for a byte-exact editor
export" (rarely needed). Constraints from the spike: the carrier is a **bare** `//` line (never
inside a quoted value — there `//` is preserved, not stripped); it is a display/interchange encoding
only — the folder is stored in the sidecar, **never** in the trunk `actor.t3d` body, so a stored body
never contains it (`actor show` generates it from the sidecar; `actor add` consumes it into the
sidecar). *(Resolves §8 R6. Supersedes the earlier `folder:`-header + mandatory-`--t3d-only` sketch;
the reviewers' pure-T3D-default concern is now moot — the default IS pure importable T3D.)*

---

## 5. Materialize — folder never reaches the map

At `level materialize`, the folder is **not emitted** to the built `.dx`/`.unr` (Decision: "Don't
emit to the map"). The map carries no folder; the actor's T3D `Group=` prop (if any) emits as today,
unchanged. Rationale: folders are editor-organization metadata, gameplay-irrelevant, and the trunk
sidecar is the source of truth. This also fully sidesteps the FName length limit that motivated the
sidecar. Add a regression: a foldered trunk materializes to a map with no folder trace and a hash
equal to the same trunk with folders stripped.

---

## 6. Stash / prefab interaction

Stash/prefab use the flat `read_state_dir` tree (`{actors/<name>.t3d, order, packages, meta.json}`),
not per-actor dirs — so there is no per-actor `folder` sidecar slot in a captured box, and captured
folders are "meaningless in a new level" (the reasoning behind today's `stashlib.with_group`). But
`stash apply` / `prefab apply` **write into the trunk** (the placement target), so they CAN stamp a
folder on the placed actors. Therefore:

- **Capture does not persist per-actor folders** (a captured set carries no folder dimension).
- **`stash apply` / `prefab apply` gain `--folder` / `--no-folder` — ADDED ALONGSIDE the existing
  `--group` / `--no-group`, not renamed** (review S1: a rename would silently drop the ability to
  stamp a T3D `Group` prop at placement, an unflagged capability regression, and would make a scripted
  `apply --group X` change meaning). The two are independent placement dimensions:
  - `--group` / `--no-group` (existing, `cli.py:117-123`; `stashlib.with_group`, `dispatch.py:332`) —
    the T3D **`Group` prop**, default = stash id / prefab basename. **Unchanged.**
  - `--folder <path>` (new, **optional, no default**) — the **sidecar**, written on placement into
    the trunk via a new `stashlib.with_folder` (sets the model field). **Absent `--folder`, placed
    actors are ungrouped** (`folder=None`) — Andrzej's R5 ruling ("unfoldered unless --folder"). There
    is no `--no-folder` on apply (ungrouped is already the default); `--group`'s own id/basename
    default is unchanged and independent.
- Placement is always a **trunk** target, so the folder always persists (the trunk-only restriction
  in §4 concerns `--target stash|prefab` on the folder verbs, not apply's placement into the trunk).
- The T3D `Group` prop on captured actors otherwise round-trips untouched (independent dimension).

---

## 7. Testing

Offline (CI, no editor):
- **Trunk round-trip:** write/read an actor with a folder; `folder` sidecar content; absent file →
  `None`; `unset` removes the file; unicode/long path. **Atomic write:** the folder lands via
  `tmp + os.replace` (assert no non-atomic `write_text` of the final path).
- **Delta-write, both directions:** a folder-only `actor folder set` persists (the §2 diff trap) —
  a body-identical, folder-changed actor IS in the written set; **`actor folder unset` (`"x"`→`None`)
  on an otherwise byte-identical actor also persists** (the symmetric trap); a truly untouched
  actor's dir is not stomped (compose-with-concurrent-writer invariant preserved).
- **Grammar validation:** accept/reject table for stored paths (empty segment, leading/trailing dot,
  metacharacters `* , / \` whitespace, case preserved).
- **Matching (drive the §3 ALGORITHM, not just the table):** parametrized cases incl. the
  boundary rules — `X.**` matches `X` itself (zero-segment `**`), `**.roof` matches a top-level
  `roof`, `*` is exactly one segment (`cast` ⊄ `castle`, segment-boundary prefix), `*.roof` ⊂
  `*.**.roof`, repeated-flag OR, case-insensitivity, **`?`/`[`/`]` in a pattern rejected**,
  **`folder=None` matches no pattern**, `--no-folder` selects exactly the ungrouped set,
  `--folder`+`--no-folder` mutually exclusive.
- **Materialize:** foldered trunk → map with no folder; canonical hash equal to folder-stripped
  trunk (folder excluded from the hash).
- **CLI guards:** `actor folder set/unset/get` on a missing actor → named error, exit 2 (never a
  traceback); invalid path → exit 2 naming the offending value; `actor add --folder` bad path → exit
  2 before any write; **any folder surface with `--target stash|prefab` → exit 2** ("folders apply
  only to a level target"); `actor folder set --to <path> <names…>` grammar parses (incl. the
  stdin-`-` names form) and rejects a missing `--to`.
- **`actor show` carrier round-trip:** default output carries `// uedcli-folder: <path>` per foldered
  block; **`actor show A | actor add -` reproduces A's folder** (parse the carrier → sidecar);
  `--t3d-only` omits the comment; an explicit `actor add --folder` overrides an incoming carrier;
  a non-carrier `//` comment in the input is ignored (not mistaken for a folder).
- **Apply:** `--group` still stamps the T3D `Group` prop (default id/basename); `--folder` stamps the
  sidecar and has **no default** — absent it, placed actors are ungrouped; the two are independent.
- **Independence:** an actor with both a `Group=` prop and a folder — both survive round-trip; setting
  a folder never touches `Group`, and vice-versa.

**Engine-facts regression (already landed by the spike):**
`test_engine_facts.py::test_t3d_import_strips_double_slash_comments` pins the `//`-strip in the
committed `core.dll` — the property that makes the `actor show` carrier safe to paste into UnrealEd.
(The folder feature itself asserts no *new* editor behavior; it relies on this pinned one.)

---

## 7b. Migration from existing `Group=` levels

Independence means existing levels (whose actors carry a T3D `Group=` prop) start with **empty
folders** — there is no automatic conversion (Decision 3: Group is not absorbed). Because folders and
`Group` are independent, that's intentional, but the "overhaul" ships a documented **opt-in recipe**
to re-fold a level that used flat `Group`s (needs the paired STDIN-`-` feature):

```
# put every actor grouped "cellblock" into folder act2.cellblock
actor find --group cellblock | actor folder set --to act2.cellblock -
```

No bulk auto-migration verb in v1 (a `--from-group` sugar could follow if wanted — inbox).

## 8. Review-gate resolutions + remaining open points

**Resolved from the two cold reviews (2026-07-18)** — folded into the sections above:
- **B1 matching-by-example → §3 now carries the normative algorithm** (regex translation +
  separator-absorption boundary rule).
- **B2 query charset → §3:** `*` is the only wildcard; `?`/`[`/`]` rejected.
- **B3/S5 stash-prefab target dead-end → §4:** all folder surfaces reject `--target stash|prefab`
  (exit 2).
- **B1(rev2) `set` grammar footgun → §4:** path moved to `--to <path> <names…>` (composes with
  stdin-`-`); "mirrors prop set" wording corrected.
- **S1 apply `--group`→`--folder` rename → §6:** `--folder` is **added alongside** `--group`, not a
  rename; both dimensions kept.
- **S3 non-atomic sidecar write → §2:** folder writes via `tmp + os.replace`.
- **S4 unset delta-diff → §2:** the changed-set diff fires on `"x"`→`None` too.
- **R1 retire `--group`? → DECIDED KEEP** (§4): single-path-per-actor forces keeping it as the
  multi-tag safety valve.
- **R4 ungrouped `get` output → DECIDED `(none)`** sentinel (§4).
- **S2/N-asymmetry, non-compositional `**.roof` → §3 ⚠ box:** kept (Andrzej's choice), documented
  loudly in `--folder` help.

**Andrzej's rulings on the remaining open points (2026-07-18 — all now closed):**
- **R2 — stored-path char set → DECIDED KEEP `[A-Za-z0-9_+-]`** ("fine for now").
- **R5 — `apply` default folder → DECIDED UNGROUPED unless `--folder`** ("unfoldered unless
  --folder"). So apply's `--folder` has **no default** — absent it, placed actors have `folder=None`;
  `--group` keeps its own id/basename default (T3D prop, independent). §6 updated.
- **R6 — `actor show` folder output → RESOLVED by the spike** (`spikes/2026-07-18-t3d-comment-tolerance/`):
  the `// uedcli-folder:` comment carrier makes the DEFAULT output both folder-round-tripping AND
  UnrealEd-importable, so the round-trip tension is gone — no `--t3d-only` needed for the pipe (§4).

**Deferred (filed to inbox):** `folder rename <old> <new>` (whole-subtree re-parent/rename);
exact-single-node match; a `--from-group` bulk-migration sugar.

## 9. Implementation touchpoints (for the plan)

`model.py` (`Actor.folder` field) · `trunk.py` (read/write the sidecar **atomically** +
`read_level_with_bodies` grows a name→folder 4th tuple element; `read_level`/callers ripple) ·
`TrunkLevelSource.load`/`save` in `dispatch.py` (`_loaded_bodies` baseline gains loaded-folders;
folder in the changed-set diff, incl. →None) · `query.py` (`_folder_matches` globstar +
`list_actors` `folders`/`no_folder` params) · a new **`folderlib.py`** for the pure path
grammar/validation + the normative match algorithm (§3) · the **`// uedcli-folder:` carrier**: an
ingest-side parse (a bare-`//`-line reader on the `actor add`/`parse_t3d` path → sidecar, carrier
stripped from the stored body) + a show-side emit (generate the comment from the sidecar) · `cli.py`
(`actor folder set|unset|get` subparser with `--to`; `actor add --folder`; `actor find
--folder`/`--no-folder`; `stash/prefab apply --folder` **added beside** `--group`/`--no-group`;
`actor show --t3d-only`) ·
`dispatch.py` (handlers; the **trunk-only target guard** on all folder surfaces; `_apply_set`
folder) · `stashlib.py` (new `with_folder`, `with_group` unchanged) · `normalize.py` (regression:
folder stays out of the canonical hash). Docs on build: `architecture.md` (the folder dimension +
sidecar), `unrealed/t3d.md` (folder is uedcli-side, not a T3D construct).
