# Terminology

## What we want

Terms kept strictly apart. **"level" never means the file; "map" never means
the abstract content.**

- **level** — the authored content / domain object (`level materialize`,
  `Level`, "level name"). Substrate-agnostic.
- **map file** — the binary on-disk artifact only (`.dx`/`.unr`); matches the
  engine's `MAP SAVE`/`MAP EXPORT` verbs.
- **T3D tree** — the directory form of a level: one directory per actor,
  `maps/<level>/actors/<name>/{actor.t3d, order_value[, folder][, labels]}`.
  The actor's name is its directory name, re-injected into the constant
  `actor.t3d`'s `Name=` at materialize; `order_value` is a per-actor LexoRank
  sidecar; the optional `folder` and `labels` sidecars hold its organization
  path and its classification tokens. No shared `order` file, no `packages`
  manifest. The level's name is the `<level>` directory name — there is no
  `name` file.
- **folder** — an actor's hierarchical, dotted organization **path**
  (`castle.tower.roof`), uedcli-side only: stored in the per-actor `folder`
  sidecar, **never** emitted to the built map, and a **separate dimension**
  from the T3D `Group=` property (which is retained unchanged). Distinct from
  the three unrelated "group" senses: the `Group=` actor prop, texture
  `Package.Group.Name`, and the `var(Group)` property category.
- **label** — an actor's flat, multi-valued classification token (`lighting`,
  `flammable`, `hero`): the cross-cutting axis a single hierarchy can't
  express — a torch is at `castle.tower` AND is `lighting` AND `interactive`
  at once. Like `folder`, uedcli-side only (a per-actor `labels` sidecar,
  **never emitted to the built map**) and **orthogonal** to `folder`, the
  engine `Group` prop, and the engine `Tag` prop. Named `label` precisely
  because "tag" would collide with `Engine.Actor.Tag`. The word is overloaded
  — the preview renderer uses "label" for a placed piece of canvas text, and
  its *selection* flag is `--annotate`; see `../architecture.md`.

## Rejected

- **One term for everything.** Collapsing breaks either way: "map" everywhere
  fights the entrenched `level materialize`/`Level` surface; "level" everywhere
  forces the awkward "level file" for a `.unr`. The split matches the engine's
  own usage — a loaded `Level` is `MAP SAVE`d to a map file.
- **"map" as the domain term.** Would require renaming the existing `level`
  verb group and `Level` model, for no gain — "you apply a level" reads
  correctly.

## Refs

`../architecture.md` "T3D tree" · `../unrealed/t3d.md`
