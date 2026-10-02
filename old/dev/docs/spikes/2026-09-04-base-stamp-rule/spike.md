# UED22 `Base=LevelInfo` MAP-IMPORT stamp rule — empirical derivation

**Question.** What exact rule does UED22 use to stamp an actor's `Base=LevelInfo` at `MAP IMPORT`?
A prior Engine.dll disassembly claimed
`Base==NULL & bCollideWorld==True & IsA(Decoration|Inventory|Pawn) & Physics ∈ {PHYS_None,
PHYS_Rotating}` (all class-default values), but `DeusEx.Pinball` (class-default `PHYS_Falling`) is
stamped — refuting the physics clause. Native's own gate
(`bStatic==False & bCollideWorld==True & Physics==PHYS_None`) is also suspect.

## Method

One T3D of LevelInfo + a sacrificial builder brush at `Actors[1]` + one instance of each of 27 real,
concrete actor classes chosen to bracket every clause (varying ancestry × class-default Physics ×
bCollideWorld × bStatic), each with a unique name/Location and **no authored `Base`, no authored
`Physics`** (so spawn-time == class default). Built with the campaign reference recipe
(`build_ued_import_built_golden.py`: `MAP IMPORT` whole-file → `MAP REBUILD` → `MAP SAVE`), then the
saved `.dx` was decoded for each probe's `Base` prop. `harness/` holds the probe matrix, trunk
builder, decoder; `golden/probe_matrix.dx` is the built reference; `test_base_stamp_rule.py` pins it.

Abstract classes are skipped (`SpawnActor` won't place them), so concrete representatives stand in
(e.g. `AmmoRocket` for Inventory, `Bartender`/`Fish`/`Fly` for Pawn).

## Truth table (measured from `golden/probe_matrix.dx`)

| Class | ancestry | class-def Physics | bCW | bStatic | Base stamped |
|-------------------------|-----------------|------------------|-----|---------|--------------|
| `DeusEx.Pinball`         | Decoration      | PHYS_Falling     | T   | F       | **YES** |
| `DeusEx.Toilet`          | Decoration      | PHYS_None        | T   | F       | **YES** |
| `DeusEx.TrashBag`        | Decoration      | PHYS_Falling     | T   | F       | **YES** |
| `DeusEx.DataCube`        | Decoration      | PHYS_Falling     | T   | F       | **YES** |
| `DeusEx.ComputerPersonal`| Decoration      | PHYS_Falling     | T   | F       | **YES** |
| `DeusEx.AlarmLight`      | Decoration      | PHYS_Rotating    | T   | F       | **YES** |
| `DeusEx.SatelliteDish`   | Decoration      | PHYS_Rotating    | T   | F       | **YES** |
| `DeusEx.Poolball`        | Decoration      | PHYS_Rolling     | T   | F       | **YES** |
| `DeusEx.CarWrecked`      | Decoration      | PHYS_None        | T   | **T**   | **YES** |
| `DeusEx.FirePlug`        | Decoration      | PHYS_None        | T   | **T**   | **YES** |
| `DeusEx.Bartender`       | Pawn            | PHYS_None        | T   | F       | **YES** |
| `DeusEx.Fish`            | Pawn            | PHYS_Swimming    | T   | F       | **YES** |
| `DeusEx.Fly`             | Pawn            | PHYS_Flying      | T   | F       | **YES** |
| `DeusEx.SecurityCamera`  | Decoration      | PHYS_Rotating    | F   | F       | no |
| `DeusEx.AmmoRocket`      | Inventory       | PHYS_Falling     | F   | F       | no |
| `DeusEx.WeaponPistol`    | Inventory       | PHYS_Falling     | F   | F       | no |
| `DeusEx.Spark`           | Effects         | PHYS_None        | T   | F       | no |
| `DeusEx.ParticleProxy`   | Effects         | PHYS_None        | T   | F       | no |
| `DeusEx.GasGrenade`      | Projectile      | PHYS_Falling     | T   | F       | no |
| `Engine.Light`           | Light           | PHYS_None        | F   | T       | no |
| `Engine.PathNode`        | NavigationPoint | PHYS_None        | F   | T       | no |
| `Engine.PatrolPoint`     | NavigationPoint | PHYS_None        | F   | T       | no |
| `Engine.AmbientSound`    | Keypoint        | PHYS_None        | F   | T       | no |
| `Engine.InterpolationPoint`| Keypoint      | PHYS_None        | F   | F       | no |
| `DeusEx.MoverCollider`   | Keypoint        | PHYS_None        | F   | F       | no |
| `Engine.Trigger`         | Triggers        | PHYS_None        | F   | F       | no |
| `DeusEx.DeusExMover`     | Mover/Brush     | PHYS_MovingBrush | F   | F       | no |

Stamped `Base` always resolves to the level's `LevelInfo`.

## The exact rule

    stamped  <=>  no authored Base
                  AND class-default bCollideWorld == True
                  AND ( IsA(Engine.Decoration) OR IsA(Engine.Pawn) )

No physics clause, no bStatic clause. Verified: the predicate over the git-tracked `uned/UED22/*.u`
corpus reproduces all 27 measured rows exactly (`test_base_stamp_rule.py`).

Clause-by-clause evidence:

- **bCollideWorld required** — `SecurityCamera` (Decoration, bCW=False) is NOT stamped.
- **Ancestry gate is real and narrow** — `Spark`/`ParticleProxy` (Effects) and `GasGrenade`
  (Projectile) all have bCW=True yet are NOT stamped: bCollideWorld alone is insufficient. Only
  Decoration and Pawn are stamped.
- **No physics clause** — Decorations/Pawns with `PHYS_Falling/Rotating/Rolling/Swimming/Flying`
  are all stamped whenever bCW=True.
- **No bStatic clause** — `CarWrecked`/`FirePlug` (Decoration, bStatic=True, bCW=True) ARE stamped.
- **Inventory is inert** — the disasm lists Inventory in the IsA set, but *no concrete Inventory
  class has bCollideWorld=True* (Inventory's default is False), so the Inventory clause can never
  fire. Neither confirmed nor refuted; harmless to keep or drop.

## Reconciliation

**Disasm** (`Base==NULL & bCollideWorld==True & IsA(Decoration|Inventory|Pawn) & Physics ∈
{PHYS_None,PHYS_Rotating}`): the `Base==NULL`, `bCollideWorld==True`, and IsA(Decoration|Pawn)
clauses are **correct**; the Inventory member is inert; the **Physics clause is WRONG** (Falling/
Rolling/Swimming/Flying decos+pawns are stamped). That is the one and only bad clause.

**Native** (`unbuilt.py` `_base_stamped`, `bStatic==False & bCollideWorld==True &
Physics==PHYS_None`): two wrong clauses and no ancestry gate.
- `Physics==PHYS_None` → false negatives (drops `Pinball` and every non-None-physics deco/pawn).
- `bStatic==False` → false negatives (drops `CarWrecked`/`FirePlug`).
- missing ancestry gate → false positives (would stamp `Spark`/`ParticleProxy`: Effects, bCW=True,
  PHYS_None, bStatic=False all pass native's gate, but UED22 does NOT stamp them).

## The required `_base_stamped` change (NOT implemented — measurement spike)

Replace the flag-only body with bCollideWorld + ancestry (drop physics + bStatic):

```python
def _base_stamped(name: str) -> bool:
    a = level.actors.get(name)
    if a is None or any(k.split("(")[0].casefold() == "base" for k, _v in a.props):
        return False
    try:
        d = cdefaults.for_class(a.cls).defaults
    except Exception:
        return False
    if str(d.get(("bcollideworld", 0))) != "True":
        return False
    return (class_index.descends_from(a.cls, "Engine.Decoration")
            or class_index.descends_from(a.cls, "Engine.Pawn"))
```

Needs a `ClassIndex` in scope; `assemble_unbuilt` already builds one (`class_index`) for the mover
check, but AFTER `_base_stamped` — move that construction above `_base_stamped`, or build one here.
(`descends_from` needs an FQCN; `a.cls` is already required qualified by the existing
`cdefaults.for_class(a.cls)` call.) Optionally add `Engine.Inventory` to the OR to mirror the
corrected disasm set — inert, so it changes no observed row.
