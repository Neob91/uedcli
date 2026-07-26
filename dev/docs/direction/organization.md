# Organization — folders and labels

## What we want

Two **independent** organizational dimensions on every actor, both uedctl-side only.
[`terminology.md`](terminology.md) defines the terms; this doc is how they are set,
managed and queried, and why there are two.

**Why two.** A `folder` is one hierarchical path per actor — good for "where does this
live," useless for cross-cutting concerns. A torch is at `castle.tower` AND is
`lighting` AND `interactive` at once. The multi-valued axis is its own dimension
rather than a loosened folder.

**Set at CREATION, on the generators.** `brush build`/`actor build` take
`--folder <path>` and `--label <l>` (repeatable). They emit the organization as T3D
comment carriers — `// uedctl-folder:` and `// uedctl-labels:` — which `actor add`
persists into the sidecars:

    brush build cube --folder castle.wall --label lit | actor add -

`brush intersect`/`brush deintersect` inherit the same generator flag set.

**`actor add` is a PURE carrier-consumer.** It has NO `--folder`/`--label` flag: it
persists whatever carriers ride the incoming T3D and nothing else. A generator is the
single place that creates an actor's identity, including its organization — one setter,
no precedence rule to remember.

**Changed afterwards on the trunk**, value on a flag, actors positional or `-` from
stdin, so `-` universally means "actors from stdin":

- `actor folder set --to <path> <names…|->` · `actor folder unset` · `actor folder get`
- `actor label add|remove --label <l> (repeatable) <names…|->` · `actor label clear` ·
  `actor label get`

There is **no `label set`** — replace-all is `clear` + `add`. On a single-valued
dimension `set` is the only way to change the value; on a multi-valued one it is
derivable, so it would be surface for nothing.
`set`/`unset`/`add`/`remove`/`clear` are producers: touched Names to stdout, the human
count to stderr, so every organization edit chains in a pipeline.

**Both dimensions work on every tree — `--tree level|stash|prefab`.** The
unify-T3D-trees invariant gives stash and prefab members the same per-actor sidecar
slot, so a level-only restriction would be an artificial asymmetry between the two
dimensions.

**Queried with `actor find`:** `--folder <pattern>`, `--label <glob>` (repeatable,
OR-combined), and `--no-folder`/`--no-label` for the unset sets — the only way to reach
them, since an unset value matches no pattern, and therefore the only way to ask "what
have I not filed yet".

**Folder pattern matching is globstar.** A **wildcard-free** pattern is a subtree
prefix: `castle` selects `castle` and every descendant. **Any** wildcard makes the
pattern a pure segment-glob with no implicit subtree: `*` matches exactly one segment,
`**` any depth (zero or more). So `castle.*` = direct children, `castle.**` = the whole
subtree (== bare `castle`), `**.roof` = a `roof` at any depth. The subtree-vs-glob
asymmetry is **deliberate and non-compositional** — `**.roof` gives the roof nodes only,
not their contents, while bare `castle` does include its contents — and it is documented
loudly in `--help` rather than smoothed over. "Every roof and everything inside" is
`--folder '**.roof' --folder '**.roof.**'`.

**Label patterns are flat and `*`-only** — labels have no hierarchy. Both dimensions
accept `*` (folders additionally `**`) and **reject** `?`, `[` and `]` with a clean exit
2, so there is no pattern-syntax asymmetry between them. Stored segments/tokens are
`[A-Za-z0-9_+-]`, matched case-insensitively, stored as authored.

**Independent of the engine `Group` prop, which is retained unchanged.** No absorb, no
derive, in either direction; an actor may carry both. `actor find --group` (the T3D-prop
filter) stays.

**Placement — `stash apply` / `prefab apply`** — merges a captured actor set or a
library prefab into the current level. It keeps **both** dimensions, independently:

- `--group` stamps the engine `Group` prop, defaulting to the stash id / prefab
  basename. Renaming it to `--folder` would have silently changed what an existing
  scripted `stash apply --group X` does.
- `--folder` sets the uedctl sidecar and has **no default** — placed actors are
  unfoldered unless asked for, rather than being silently filed under a name the user
  never chose.
- **A fresh batch token is ALWAYS minted**, exactly as `actor duplicate` does:
  `prefab-<name>-<rand>` / `stash-<id>-<rand>`, with the source name sanitised into the
  label charset. Placed actors carry `inherited ∪ {batch token} ∪ {explicit --label}` —
  an explicit `--label` is purely **additive** and never replaces the token, so the
  batch stays addressable by a collision-free handle after the pipeline ends. The
  readable middle segment means `actor find --label 'prefab-castle-tower-*'` finds every
  placement of that prefab, not just the last one.

**`actor duplicate` uses labels as the batch handle** the same way. Copies carry
`inherited ∪ {dup-<rand>} ∪ {explicit --label}`. Placement is **required** (`--by` or
`--at`) — an explicit `--by 0,0,0` is the deliberate duplicate-in-place escape hatch,
so an accidental invisible overlapping copy is an error rather than a warning.

**The carrier is a T3D comment, so `actor show` output is both round-tripping and
editor-importable.** UnrealEd's importer silently strips `//` line-comments, so the
default output carries the organization for uedctl and is dropped without warning by the
editor. `--t3d-only` suppresses the comments for a byte-exact editor export.

**Never emitted to the built map, never in the level hash.** Both are editor-organization
metadata with no gameplay meaning; the sidecar is the source of truth, which also
sidesteps UnrealEd's FName length limit on `Group=` for deep dotted paths. The
consequence is accepted: open the built map in UnrealEd and the organization is not
there — only the engine `Group` prop, which uedctl leaves untouched.

**Enumeration lives under `actor` too.** `actor folder list` prints the distinct folder
paths in use, `actor label list` the distinct labels — answering *what exists*, which
`actor find --folder/--label` (find actors BY one) cannot. There is **no top-level
`folder`/`label` verb family**: they organize actors, `actor` is where a user looks, and a
parallel namespace would duplicate the query surface.

## Rejected

**Naming and storage**

- **Keeping the name `group`.** Collides three ways — the T3D `Group=` actor prop, texture
  `Package.Group.Name`, and the property-browser `var(Group)` category.
- **Naming the flat dimension `tag`.** Collides with the real `Engine.Actor.Tag` property
  (reached via `find --prop Tag=`) — the same overload `folder` was invented to avoid.
  `keyword`, `mark` and `badge` were also weighed; `label` won once it was freed by renaming
  `actor preview`'s annotation flag `--labels` → `--annotate`.
- **Deferring that preview flag rename to a separate later step** — the best word was taken
  immediately rather than left occupied.
- **Storing the folder in the T3D `Group=` prop.** Deep dotted paths overflow UnrealEd's
  FName length limit; a sidecar beside `order_value` also merges per-actor under `git merge`
  like the rest of the trunk.
- **Absorbing an ingested `Group=` into the folder** on `actor add`/import. The two are
  independent; neither derives from the other.
- **Emitting the folder to the built map** — either the leaf segment, or the full path when
  it fits.

**Two dimensions, not one**

- **Overloading `folder` with multi-membership.** Turns a clean tree into a tag-set, makes
  the word "folder" lie, and leaves every folder operation (`set`/`unset`/`find`/rename)
  ambiguous.
- **Keeping the old comma-list multi-membership** on the hierarchical dimension.
- **Renaming `stash apply --group` → `--folder`.** Would drop the ability to stamp a T3D
  `Group` prop at placement and silently change what an existing scripted invocation does.
- **Retiring `actor find --group`.**
- **Defaulting the placement folder from the stash id / prefab basename** — it invents
  organization the user never asked for. The *batch label* carries that provenance instead,
  where it is additive rather than a silent default.
- **Restricting label surfaces to the level tree.** The unify-T3D-trees invariant gives
  every box the same sidecar slot, so a level-only guard is an artificial asymmetry.

**Patterns**

- **Bare pattern = exact match only.** Bare = whole subtree.
- **A single any-depth wildcard.** Cannot express "direct children only".
- **A `***` "one-or-more" token.**
- **`?` and `[`/`]` as wildcards**, on either dimension — including the `[abc]` character
  class briefly allowed on `--label` by free fnmatch, which left labels and folders with
  different pattern grammars for no reason.

**CLI shape**

- **Keeping `--folder`/`--label` on BOTH the generators and `actor add`.** Two setters plus
  a precedence rule; the single-setter model wins.
- **Scoping the generator flags to `brush build` only** — leaves `actor build`
  half-converted.
- **Keeping `--group` as a dedicated `brush build` flag** for discoverability. It was a plain
  `Engine.Actor.Group` Name prop with no abstraction on top, so it is redundant with
  `--prop Group=` — unlike `--csg`/`--solidity`/`--texture`/`--rotate`, which each carry
  semantics beyond a raw prop and stay.
- **Two greedy positionals for `folder set` (`set <names…> <path>`).** Ambiguous, and it
  breaks the stdin-`-` compose. The path goes on `--to`.
- **Labels positional with actors only via `-`.** Breaks the mutating-verb-family convention
  and makes inline actor names awkward.
- **A distinct `--to`-style flag for the label mutation value.** It is the same token as the
  `find --label` filter — same meaning, different verb.
- **Keeping a `label set` sub-verb.** Derivable from `clear` + `add`.
- **Promoting `folder`/`label` to top-level verb families.**
- **Dropping `--no-folder`/`--no-label`.** They are the only route to the unset sets, since
  an unset value matches no pattern.
- **A v1 whole-subtree `folder rename`/move.** Deferred, still parked.

**Interchange carrier**

- **The unknown-property carrier `UedctlFolder="…"`.** It works, but spams a per-actor
  `Unknown property in defaults` warning on import.
- **`/* */` and `;`** — not comment syntax to the T3D importer at all; they survive only as
  incidental no-`=` skipped lines.
- **Pure-T3D default with a `--with-folder` opt-in.** The carrier removes the
  round-trip-vs-compatibility tension entirely, so the opt-in is unnecessary.
- **Carrying organization out-of-band** (a side channel beside the T3D). Keeps the T3D pure,
  but `actor show | actor add -` stops round-tripping — and that pipeline is what the whole
  CLI is built on.

**Batch handles**

- **A batch token minted only when `--label` is absent**, on either `duplicate` or
  placement. A named batch would then be addressable only by a name that might already be
  in use elsewhere.
- **No auto-minted token at all.** Cleanest label sets; loses the re-addressable-batch
  guarantee that is the whole point.
- **A bare `<kind>-<name>` token with no random suffix.** Readable, but applying the same
  prefab twice gives both batches the same label, so the one just placed cannot be isolated.
- **A bare in-place `duplicate` as a warning rather than an error.** Accidental invisible
  overlapping copies; `--by 0,0,0` makes the overlap intentional.
- **Deferring `--by`/`--at` to a placement follow-up** — one coherent duplicate overhaul.

## Refs

`../architecture.md` "Folders" / "Labels" (`folderlib.py`, `labellib.py`) ·
`../unrealed/t3d.md` "Comments & unknown properties on import" ·
`../spikes/2026-07-18-t3d-comment-tolerance/`
