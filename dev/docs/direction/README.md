# direction/ — what the owner decided

One doc per topic, **revised in place**: no supersession, no dated history, no ledger. Git keeps the
past. Each topic states **What we want**, **Rejected**, and **Refs**.

**Agents may NEVER write this tree without the owner's explicit yes** — see `CLAUDE.md` "Direction
docs" for the rule. This README is the exception: index rows only, and never an `@` import.

Siblings: `../rationale/` (why the code is that way — agent-owned), `../architecture.md` (what IS),
`../rules/` + `CLAUDE.md` (process).

**Migration in progress** — a *(pending)* row still lives in `../direction.md`; read it there.
[`../rationale/MIGRATION.md`](../rationale/MIGRATION.md) records where every old entry went.

| Topic | Covers | |
|--------------------------|--------------------------------------------------------|---
| [`scope.md`](scope.md) | a generic UnrealEngine-1 tool; Deus Ex as one substrate | ✅ |
| `projects-and-config.md` | projects, substrates, the global CLI, layered packages | *(pending)* |
| [`trunk-and-editor.md`](trunk-and-editor.md) | the T3D trunk as source of truth; the editor as build tool | ✅ |
| [`organization.md`](organization.md) | folders (hierarchical) and labels (flat, multi-valued) | ✅ |
| [`materialize.md`](materialize.md) | `level materialize`; lighting/BSP as build output | ✅ |
| [`safety.md`](safety.md) | never irretrievably clobber | ✅ |
| `containers.md` | container isolation; the code/content substrate split | *(pending)* |
| `generators.md` | stateless T3D producers | *(pending)* |
| `packages.md` | one package-format core | *(pending)* |
| `asset-catalog.md` | texture / class / sound / music; the tool does not infer | *(pending)* |
| [`terminology.md`](terminology.md) | level, map file, T3D tree, folder, label | ✅ |
| [`conventions.md`](conventions.md) | no back-compat cruft; explicit, discoverable, model-side | ✅ |
| [`process.md`](process.md) | how the project is run — gates, worktrees, the docs model | ✅ |
