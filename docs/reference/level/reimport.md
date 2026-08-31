# level reimport

**`level reimport`** is `level import`'s sibling for a level you already have in trunk: it decodes
a compiled map file the same way, but instead of creating a fresh tree it MATCHES actors by name
against the trunk you point it at, so actors it doesn't mention are left completely alone —
their body, their folder/label, and their CSG order.

Use it when you (or someone else) opened the level's materialized `.dx`/`.unr` directly in
UnrealEd — to do something uedcli can't yet express — and want those changes back in trunk without
losing history or metadata for everything you didn't touch. `level import --overwrite` also
replaces an existing level, but wholesale: every actor is rewritten fresh, folders/labels are lost,
and the diff touches the entire level regardless of how small the real edit was. `level reimport`
is the targeted alternative.

```
level reimport MAPFILE --tree level/NAME [--force]
```

- **`MAPFILE`** is the compiled map to read — same rules as `level import`.
- **`--tree level/NAME`** names the level to reimport INTO, and it must already exist (the
  opposite of `level import`'s create-only destination) — use `level import` first if it doesn't.
  Defaults to the level named by `$UEDCLI_LEVEL`, like an ordinary content verb.
- **Matching is by actor name.** An actor present in both the trunk and the map is updated in
  place; one only in the map is added; one only in the trunk is deleted — including an actor added
  to the trunk after the materialize that produced MAPFILE (by another session, or by hand):
  reimport only knows "in the map, or not", the same as `level import --overwrite`. A matched
  actor's folder/labels are carried over from the trunk unchanged, whether or not its body changed
  — the compiled map format carries neither. Every added actor gets one shared `reimport-<hex>`
  label, freshly minted per invocation, so `actor find --label reimport-<hex>` finds them for
  review afterward.
- **CSG order (`order_value`) is recomputed for brushes only** — point actors don't participate in
  CSG, so their order is never touched. A brush whose relative position among brushes didn't
  change keeps its exact `order_value` (no diff); a moved or newly added brush gets a freshly
  computed one.
- **`--force`** is required if the reimport would modify or delete more than 20% of the trunk's
  actors — a guard against reimporting the wrong file. Ordinary repositioning (`Location`/
  `Rotation` only) and pure additions never count toward that percentage.
- **Output:** the reimported level's actor names go to stdout, one per line; the summary (added/
  deleted/changed counts) goes to stderr.

```
export UEDCLI_LEVEL=nyc-study
level materialize --out /tmp/nyc-study.dx
# ... open /tmp/nyc-study.dx in UnrealEd, tweak something, save ...
level reimport /tmp/nyc-study.dx --tree level/nyc-study
```

Everything `level import`'s "What import leaves out" and "Requirements and caveats" sections say
about the decode itself — the dropped builder brush and viewport cameras, the strict class/texture
validation, folders and labels having no equivalent in a compiled map — applies here too.

See also: [`level import`](import.md), [`level materialize`](materialize.md).
