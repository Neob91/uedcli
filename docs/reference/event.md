# event

**`event graph [--dot | --json]`** reports how the level's actors are wired to trigger each other —
**offline, model-side** (no editor; it does read the game's `.u` packages, because a Mover is a node
even with no eventing props — see [Projects](../README.md#projects-uedclitoml)). An actor's **`Event`** property
is the event it *fires*; another's **`Tag`** property is its *receiver* identity. A directed edge
**A → B** means `A.Event == B.Tag`.

- **Default (text):** one wiring per line to **stdout** —
  `Trig (Engine.Trigger) --OpenDoor--> Door (Engine.Mover)`; the summary + lint go to **stderr**.
- **`--dot`:** Graphviz DOT to stdout (`uedcli event graph --dot | dot -Tpng -o wiring.png`).
- **`--json`:** a `{nodes, edges, lint}` object.

The **lint** reports `dangling_event`, `unreachable_tag`, `unreachable_mover`, and `cycle`. It
**exits 0 even with findings** (a query verb — lint is advisory; grep the output for CI). Only an
explicitly-set, non-empty `Tag` counts as a receiver.

See also: [`level doctor`](level/doctor.md), [`mover`](mover.md).
