# level doctor

**`level doctor [--json] [--severity {info,warn,error}] [--category NAME]…`** statically checks the
level for the BSP/geometry problems that cause holes, HOMs, and invisible walls — **fully offline,
no editor.** It flags: degenerate faces UnrealEd will silently drop (too few vertices, zero area,
non-convex, non-planar); brushes that aren't watertight (open/duplicated/back-wound edges); solidity
mistakes (a portal marked semisolid); gross CSG-order errors (an additive brush buried inside a later
subtract, a subtract that carves nothing); and scale issues. Each finding names the brush, poly,
world coordinate, engine symptom, and fix.

**What `level doctor` will and will not find.**

`doctor` checks whether the level is mechanically well-formed: things objectively broken and
decidable from the trunk alone. "Broken" means the engine or data cannot work as authored, not that
a human would judge the result poor.

The dividing line is intent: `doctor` reports only what is wrong no matter what the author meant. A
dangling `Event` fires into the void; a light inside a solid lights nothing. But `doctor` cannot
know what a space is meant to be, so it does not judge passages: it can measure the free gap between
two brushes, but cannot tell a deliberately sealed wall from an accidentally blocked doorway — both
are the same geometry. Any check that needs to guess the author's intent is out of scope
permanently. *(Owner ruling and rationale, 2026-07-26.)*

In scope:

- **Math and geometry** that breaks or burdens the BSP — degenerate/non-planar/non-convex faces,
  brushes that aren't watertight, solidity mistakes, CSG-order errors, scale problems.
- **Zoning** problems of the same kind.
- **Obvious footguns with an objectively wrong answer** — e.g. an `Event` matching no actor's `Tag`
  (it fires into the void), or a light buried inside solid geometry (it lights nothing).

It will not find gameplay or style problems, and a clean report says nothing about them. Out of
scope by design:

- whether a corridor or doorway is comfortable to move through, or geometry protrudes into an
  entrance;
- whether a decoration is well placed, correctly oriented, or seated on its surface;
- whether the level has the trim, edge detail, or finish a real space would have;
- whether it is well lit, legible, or fun.

These are level-design quality; they need a human or an independent reviewing agent looking at
renders. A level can be `no issues found` and still be cramped, ugly and half-finished. *(Owner ruling, 2026-07-26.)*

- Categories: `degenerate, watertight, convex, planar, solidity, csg_order, scale`. `--category`
  takes one; repeat it to OR several (`--category watertight --category convex`). Exact,
  case-insensitive; an unknown category exits 2 listing the valid ones.
- `--severity` / `--category` filter what's **shown**; the **exit code always reflects ALL findings**
  (non-zero if any ERROR exists, regardless of the filter), so it works as a CI gate.
- It is a **high-recall per-brush predictor**, not a completeness guarantee: holes that only emerge
  from how brushes split each other during the build (slivers, T-junction cracks) need the build
  itself.
- **It needs the game's code packages on the search path** (a project + `~/.uedcli/config.toml`):
  the watertight check applies to closed solids — world brushes *and movers* — and mover-ness is a
  class-hierarchy question (see [Projects](../../README.md#projects-uedclitoml)). With no resolver it exits 2
  naming the verb and what is missing, rather than reporting a partly-checked level as clean.

See also: [`level materialize`](materialize.md) (the advisory BSP health checks after a real build), [`event graph`](../event.md).
