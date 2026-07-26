# uedctl — direction (what we're building toward)

This is the **compiled target**: the coherent end-state uedctl is being built toward, stated
in the present tense even where the code doesn't match yet. It is *synthesized from*
[`decisions.md`](decisions.md) — newer decisions override older ones and the superseded points
are dropped here (this doc shows the **net** philosophy, not the history). Each section cites
the decision entries it distills.

How the three dev docs relate:

| Doc | Role | Mutability |
|---|---|---|
| [`decisions.md`](decisions.md) | the **ledger** — every choice + rejected alternatives, timestamped | append-only, never reworded; supersession via new entries |
| **`direction.md`** (this) | the **compiled target** — what we want, conflicts resolved | rewritten/reconciled as decisions land; superseded points removed |
| [`architecture.md`](architecture.md) | **what is** — current implementation | tracks the code |

**Maintenance rule:** when a decision is made or superseded, reconcile this doc. If `direction.md`
and `architecture.md` disagree, that gap is intended (it's the work not yet done); if `direction.md`
and the latest `decisions.md` disagree, this doc is stale — fix it.

---

## Scope: a generic UnrealEngine-1 tool

**MIGRATED** → [`direction/scope.md`](direction/scope.md).

## Projects, substrates, and the global CLI

**MIGRATED** → [`direction/projects-and-config.md`](direction/projects-and-config.md).

## The trunk and the editor

**MIGRATED** → [`direction/trunk-and-editor.md`](direction/trunk-and-editor.md).

## Terminology

**MIGRATED** → [`direction/terminology.md`](direction/terminology.md).

## Folders and labels

**MIGRATED** → [`direction/organization.md`](direction/organization.md).

## Materializing the map file

**MIGRATED** → [`direction/materialize.md`](direction/materialize.md).

## Safety

**MIGRATED** → [`direction/safety.md`](direction/safety.md).

## Container isolation

**MIGRATED** → [`direction/containers.md`](direction/containers.md).

## Generator pattern

**MIGRATED** → [`direction/generators.md`](direction/generators.md).

## One package-format core

**MIGRATED** → [`direction/packages.md`](direction/packages.md).

## The asset catalog: uedctl lists and shows, the LLM supplies meaning

Level design by an LLM agent needs to **discover** what can be placed, not just place it. One
**asset catalog engine** serves four kinds — **texture, class, sound, music** — each with its own CLI
noun and the same verb family (`list`/`search`/`show`/`preview`/`classify`/`tags`/`prewarm`);
"unified" means one implementation, never a `--kind` selector on a generic noun.

**The tool does not infer.** It does four things: **lists** what exists on the composed search path;
**reports facts literally stored in the package** (image dimensions, mesh bbox, collision
radius/height, pivot, parent class, `DrawType`); **produces the picture** (decodes a texture, renders
a mesh natively); and **stores + queries the classification it is handed**. What an asset *is*, what
it is *for*, and *where the game uses it* are the LLM's findings, recorded as classification — never
numbers the tool computed, which would be unreviewable and uncorrectable. The one deliberate
exception is **texture colours**, pre-filled from that texture's own pixels and ordered by
importance, so colour search works before any classification exists.

Mechanically: a lazily-built per-`(kind, package)` derived index gated on a
`(realpath, size, st_mtime_ns)` stat tuple, a content-addressed per-user preview cache, and
**git-tracked classifications sharded one file per asset** so concurrent agents never merge-conflict.
Identity is the **content hash** where content exists and decodes (textures) and the **name**
otherwise (class, sound, music) — so a changed texture simply reads unclassified and its old
classification becomes a prunable *outdated entry*, with no `stale` flag to maintain. Two verbs, two
jobs: **`show` returns facts + classification, `preview` returns image artifacts** — and `preview` is
the *only* producer, so no exploratory `list`/`search` can trigger a long render. Classification is
batch-capable (`classify set -` reads JSONL) and a **byproduct of looking** (`preview --skeleton`
emits fill-in rows for exactly the refs just previewed), never a bulk campaign. Cache eviction lives
on the existing `cache` noun. *(decisions: unified asset catalog 2026-07-25 03:40; the tool does not
infer 2026-07-25 05:10; spec `specs/2026-07-25-unified-asset-catalog.md`)*

## Conventions (no back-compat cruft; explicit, discoverable, model-side)

**MIGRATED** → [`direction/conventions.md`](direction/conventions.md).
