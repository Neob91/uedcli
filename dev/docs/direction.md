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

## The asset catalog

**MIGRATED** → [`direction/asset-catalog.md`](direction/asset-catalog.md).

## Conventions (no back-compat cruft; explicit, discoverable, model-side)

**MIGRATED** → [`direction/conventions.md`](direction/conventions.md).
