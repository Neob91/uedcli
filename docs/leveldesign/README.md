# Level design with uedcli

Practical guidance for building good, buildable **UnrealEngine-1** levels **with uedcli** — what makes
a level work, mapped onto the verbs you actually run. You author a git-tracked **T3D trunk** with small
composing verbs; the editor is only ever touched to `level materialize` / `level preview`.

This user area splits by scope:

- **[general/](general/)** — the **engine-generic craft**: geometry & BSP, zones, lighting, textures,
  movers, actors, shapes, human scale, design craft, and full step-by-step **recipes** (water, skybox,
  glass, doors, lifts, fire & fog). Everything here applies to any UnrealEngine-1 game.
- **[deusex/](deusex/)** — the **Deus Ex-specific** layer: the `DeusEx*` class catalog (movers,
  decorations, hackable devices), `ScriptedPawn` NPCs and alliances, DX gameplay wiring, the `CoreTex*`
  texture palette, DX human-scale numbers, and the **immersive-sim design philosophy** that makes a
  Deus Ex level a *Deus Ex* level.

Start in **general/** for craft that transfers everywhere; drop into **deusex/** when you need a DX
class name, a DX dimension, or the multi-path immersive-sim approach.

---

## The composing pattern

uedcli has no monolithic "make a room" command. Instead small verbs pipe together. *Generators* print a
T3D snippet to stdout; `actor add -` writes it into the trunk; per-surface and per-actor edits run
model-side (no editor):

```
# carve a room, then add a detail pillar inside it
brush build cube --csg subtract --width 512 --breadth 512 --height 256 --texture CoreTexMetal.ClenGrayMetal_A | actor add -
brush build cube --csg add --solidity semisolid --width 32 --breadth 32 --height 256 | actor add -

# place a light
actor build Engine.Light --prop LightRadius=8 --at 128,128,200 | actor add -

# texture faces of a brush
brush poly find Wall1 | brush poly set - --texture CoreTexMetal.ClenGrayMetal_A --add-flag Masked

# build a door mover, then key its open pose (a two-pose door already has NumKeys=2)
brush build cube --mover-class Engine.Mover --width 64 --breadth 8 --height 112 | actor add -   # prints the mover's name
mover key move <that-name> 1 --from-base --to 0,0,112   # open pose (offset from base): slides up its own height, a portcullis
```

The four verb families you compose:

| Family                                                    | What it does                                                                   | Example |
| --------------------------------------------------------- | ------------------------------------------------------------------------------ | --- |
| `brush build <shape>`                                     | *generator* — prints a T3D actor (a CSG brush or a mover)                      | `brush build cylinder --height 256 --radius 128 --sides 8` |
| `actor build <Class>` / `actor add -`                     | *generator* / *writer* — build a point actor; write any snippet into the trunk | `actor build Engine.Light --prop … \| actor add -` |
| `brush poly find` / `brush poly set` / `brush poly align` | per-surface texture + flag + alignment edits                                   | `brush poly find Room1 --facing +Z \| brush poly set - --texture …` |
| `actor prop set` / `actor order` / `mover key`            | per-actor property, CSG-order, and mover-keyframe edits                        | `actor prop set Door1 MoveTime=1.5` (`bLocked` etc. are DX `DeusExMover` props — see deusex/) |

**How it builds.** The T3D trunk is the source of truth (committed to git). `level materialize` drives
UnrealEd to compile the trunk into the `.dx`/`.unr` map file; `level preview` renders stills. You never
edit inside the editor by hand — the verbs write the trunk, the editor only builds it.

---

## Reading the guides

- Terms: **[ENGINE]** = any UnrealEngine-1 game · **[DX]** = Deus Ex only. In this general area
  everything is [ENGINE]; DX-only facts live under [deusex/](deusex/).
- A light ✅ marks a fact verified against the real editor/binary; 📖 marks community-tutorial lore
  (the mechanism is real, exact values may vary). These guides cover only what you can **author** — the
  verbs, placeable classes, and their editor-**editable** properties. Engine-internal / non-editable
  properties, binary citations, and the asset-creation / modding / editor-GUI depth are out of scope
  for these user guides.
- Two "group" senses differ and neither is uedcli's `folder`: a texture's `Package.Group.Name` (browser
  convenience) vs the T3D `Group=` actor property. uedcli's own **folder** (`actor find --folder …`) is a
  third, separate organizational dimension that never reaches the built map.

**The Deus Ex design philosophy** — problems-not-puzzles, multiple keyed solutions, readable stealth,
environmental storytelling — is the crown jewel and lives under [deusex/](deusex/). The engine-generic
craft it builds on (proportion, killing the box, sightlines, flow) is in
[general/design-craft.md](general/design-craft.md).
