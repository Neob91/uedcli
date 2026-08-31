# level import

**`level import`** goes the opposite way from `materialize`: it takes an already-compiled map file
(`.dx`/`.unr`) and turns it back into a T3D tree you can query, diff and edit with every ordinary
verb. Use it to study how an existing map is built, to lift a room or a prop out of one, or to
compare a map against your own.

It reads the map file's bytes **directly**. No UnrealEd, no container, no game — fast and works
anywhere, unlike `materialize`.

```
level import MAPFILE --tree KIND/NAME [--overwrite]
```

- **`MAPFILE`** is the compiled map to read, relative to the current directory. A file that is
  missing, unreadable, or not an Unreal package **exits 2** naming it.
- **`--tree KIND/NAME`** is the **destination, which import creates** — `level/NAME` writes a new
  level trunk at `maps/NAME/`, `stash/NAME` writes a new stash entry. `prefab/…` is refused: a
  prefab is a small reusable fragment, not a home for a whole level.
- **`--overwrite`** permits replacing an existing destination (default: refuse, exit 2). The check
  runs **before the map file is read**, so a refusal touches nothing. An existing but *empty* level
  directory does not count as existing, so retrying a failed import needs no flag.
- **Output:** the imported actor names go to **stdout**, one per line, so you can pipe them onward;
  the summary (how many actors, what was dropped) goes to **stderr**.

```
level import ~/DeusEx/Maps/02_NYC_Street.dx --tree level/nyc-study
export UEDCLI_LEVEL=nyc-study
actor find --subclass-of Engine.Light      # now query it like any other level
```

## What import leaves out

A saved map is the editor's workspace, not a clean inventory of level content — it also contains the
tools the designer happened to be holding. Import drops two kinds as apparatus rather than content:

- the **builder brush** — the red scratch shape used to sculpt geometry before committing it. Every
  saved map has exactly one. If kept, rebuilding the map later would place it alongside the fresh one
  the editor makes for itself, and the two would collide over a name.
- the **viewport cameras** — one `Camera` actor per editor viewport open at save time (four to eight
  in a typical map).

Everything else is imported as it stands, with its properties and brush geometry.

## Requirements and caveats

- **A project is required**, and its configured package paths must contain the classes the map uses.
  Import reads each class's definition to know what its stored properties mean, and each class's
  defaults to know which values were changed from them.
- **Import is strict.** Every class and every polygon texture the map references must exist on the
  package path; if one does not, the whole import **exits 2 naming it** rather than writing a tree
  with references that cannot be rebuilt. Importing a map that needs mod packages means installing
  those packages first.
- **Folders and labels start empty** — a compiled map has no equivalent to recover.
- **References between actors keep the source map's name.** A property pointing at another actor
  reads `Class'<sourcemap>.Other'` — a faithful record of the original, but pinned to the old map's
  name rather than rebinding to your new level's.
- **Resources embedded inside the map file itself are a rough edge.** Some maps store a texture or a
  sound *inside* the map file rather than referencing a shared package (the `myLevel` pseudo-package).
  Such a reference resolves to nothing on your package path: on a **brush face** it is caught by the
  validation above and the import **exits 2 naming it**; anywhere else — an actor property such as a
  decoration's `Skin` — it is **imported as written** and left dangling, since validation covers
  classes and face textures, not every object reference. A dangling reference does no harm until you
  rebuild the map, which will not find it. Extracting embedded resources into a real package first is
  the way round it, and is not yet built.
- **Maps built by uedcli's own native builder import without brush geometry**, because that builder
  keeps each shape only in the compiled world and leaves the per-brush copy empty. Editor-built maps
  (all retail content) carry both and import fully.

See also: [`level reimport`](reimport.md), [`level materialize`](materialize.md).
