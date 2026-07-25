# Deus Ex level design with uedctl

Deus Ex is **one substrate** running on the generic UnrealEngine 1 core. Everything about carving
geometry, sealing zones, lighting, texturing, and movers is engine-level craft — it lives in the
**general guides** ([`../general/`](../general/)) and applies to any UE1 game. **These guides cover only
what is Deus-Ex-specific**: the classes DX ships, the NPCs, the trigger/flag wiring, conversations and
computers, the real DX human-scale numbers, and the immersive-sim design philosophy that makes a level
feel like *Deus Ex*.

You author the same way everywhere — a git-tracked T3D trunk, built with composing verbs:

```
actor build DeusEx.MJ12Troop --at 512,256,80 | actor add -     # place a DX class
class list --subclass-of DeusEx.ScriptedPawn                    # discover what's available
actor build DeusEx.JCDentonMale | actor add - | actor prop get - CollisionRadius   # decode a default
```

Terms: **[DX]** = Deus Ex only · **[ENGINE]** = any UnrealEngine 1 game (covered in the general guides).

---

## The DX topic guides

| Guide                                                              | What it covers |
| ------------------------------------------------------------------ | --- |
| [`classes.md`](classes.md)                                         | The DX class catalog a mapper reaches for — movers, zones, hackable devices, pickups, decorations, level info — and how to place/discover them. |
| [`npcs.md`](npcs.md)                                               | Populating a level with `ScriptedPawn`: orders, alliances, reactions, inventory, and the pathnode-first workflow. |
| [`gameplay-wiring.md`](gameplay-wiring.md)                         | The DX trigger vocabulary: flags, goals, logic gates, dispatchers, hackable devices, particle emitters, and the camera→computer feed. |
| [`conversations-and-computers.md`](conversations-and-computers.md) | A user-level overview of wiring conversations, computers, and datacubes. |
| [`human-scale.md`](human-scale.md)                                 | The real, uedctl-decoded DX numbers: player size, jump/step, door/stair dimensions, device strengths. |
| [`design-philosophy.md`](design-philosophy.md)                     | The immersive-sim craft — problems-not-puzzles, multiple solutions, systemic consistency, legibility. The highest-value DX knowledge. |

## Step-by-step recipes

Task-by-task walkthroughs live in [`recipes/`](recipes/) — concrete command sequences for common DX
authoring jobs (place a locked door, wire a keypad to it, set up a guard patrol, and so on).

## See also

- [`../general/`](../general/) — the engine-level craft (geometry, BSP, zones, lighting, textures,
  movers) that DX inherits. **Read these first** — DX only adds to them.
- [`../README.md`](../README.md) — the top-level level-design index.
