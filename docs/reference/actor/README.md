# Actors

Query, mutate, and organize actors. See also [diagram](diagram.md) for rendering,
[brush](../brush/README.md) for per-surface geometry once an actor is a brush, and
[leveldesign/general/actors.md](../../leveldesign/general/actors.md) for the level-design craft
(folders, labels, and actor organization in practice). For a worked multi-command example, see
[the door mover flow](../../usage/door-mover-flow.md).

| Command | Query/mutate | What it does |
|---|---|---|
| [`actor find`](find.md) | query | print matching actor names, one per line, for piping |
| [`actor show`](show.md) | query | print named actors' full canonical T3D blocks |
| [`actor bbox`](bbox.md) | query | the world axis-aligned bounding box enclosing a set of actors |
| [`actor prop get`](prop.md) | query | print effective property values |
| [`actor folder get`](folder.md) | query | print each actor's uedcli-side folder path |
| [`actor label get`](label.md) | query | print each actor's uedcli-side labels |
| [`actor add`](add.md) | mutate | write a T3D snippet into the trunk as new actors |
| [`actor duplicate`](duplicate.md) | mutate | copy actors under fresh names, offset or anchored |
| [`actor delete`](delete.md) | mutate | delete actors, restoring swept neighbours |
| [`actor move`](move.md) | mutate | move a single actor |
| [`actor rotate`](rotate.md) | mutate | rotate a group of actors around a pivot |
| [`actor order`](order.md) | mutate | reorder existing actors' CSG precedence |
| [`actor prop set/unset`](prop.md) | mutate | set or clear properties in one atomic, schema-validated edit |
| [`actor folder set/unset/rename`](folder.md) | mutate | manage the uedcli-side folder |
| [`actor label add/remove/clear`](label.md) | mutate | manage the uedcli-side labels |
| [`actor build`](build.md) | — | write a point-actor T3D for a given class (generator) |

*query — model-side, instant, no editor; mutate — model-side, rewrite the trunk.*
