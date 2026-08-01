# Reserve a `mount:`/`faces:` tag namespace on class shards, validating shape only?

## Context

Spec §5, §8.2. Mount facts ("wall-mounted, face on local +X") cannot be derived — §0 forbids the tool
inferring them — but an LLM reading the thumbnail plus the signed extents can write them as tags in the
same loop that fills the rest. The tag-normalizer only strips and lowercases, so `mount:wall` /
`faces:+x` already survive intact, but nothing reserves or validates them.

- **Proposed:** a tag matching `^(mount|faces):` is namespaced. `faces:` requires an axis token
  (`+x -x +y -y +z -z`); any other `faces:` value **exits 2** naming it. `mount:` requires a non-empty
  value; the value is otherwise free text. Validate **shape only, never meaning** — these stay ordinary
  tags for `search --tag`, `tags`, `unset --tags`; nothing new plumbs them.
- **At stake:** without the check a typo (`faces:foward`) ships silently and never filters. With it, a
  malformed handed-in classification is refused — storage hygiene, not inference.
- **Direction default:** `direction/asset-catalog.md` says the tool "stores and queries the
  classification it is handed" and "does not infer"; a shape-only check is consistent with that (it
  refuses malformed input, it does not compute meaning). But the doc does not name this namespace, so
  reserving it is an owner call. The **meaning vocabulary** (what `mount:` values exist, how `faces:`
  relates to the thin extent axis) is a separate craft claim — see Q `value-framing-and-craft-line`.

**Recommendation:** adopt the shape-only reservation. It is the minimum that makes the namespace
reliable without crossing into inference.

## Answer

<!-- Empty = open. -->
