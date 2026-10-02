# CSG combining a stash

CSG combining a stash pipes a captured actor set through a CSG generator instead of applying it
as-is: `stash show` prints the set's T3D, `brush intersect` welds
it into one solid, and `actor add` writes the result into the trunk.

```bash
uedcli stash show arch | uedcli brush intersect - | uedcli actor add -
```

There is no `stash intersect`/CSG-combine verb — the technique is this pipe, not a dedicated
command; see [`stash`](../reference/stash.md) for the negative fact and
[`brush intersect`/`brush deintersect`](../reference/brush/intersect.md) for the generator itself.

Reference: [`stash`](../reference/stash.md), [`brush intersect`/`brush
deintersect`](../reference/brush/intersect.md), [`actor add`](../reference/actor/add.md).
