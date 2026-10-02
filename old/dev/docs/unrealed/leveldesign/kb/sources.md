# Sources, provenance & residual gaps

Evidence behind the claims in `kb/`: the sources crawled (with scope), the binary verifications
against the shipped Deus Ex packages, the confidence tiers, the access notes for re-running the
crawl, and the residual gaps external reading cannot close.

Every claim about UnrealEd behavior carries its evidence; an uncited assertion cannot be trusted.
This KB was built by a multi-pass crawl of the community tutorial corpus, reconciled against the
shipped game binaries and uedcli's offline decoders — the binaries win every disagreement.

---

## 1. Confidence tiers (what the markers mean)

| Marker | Tier | Meaning |
|---|---|---|
| **✅** | uedcli-used / live-verified | a fact uedcli exercises, or live-verified against the running editor. |
| **🔬** | binary-probed | read directly from the shipped `DX/System/*.u` / `DX/Textures/*.utx` this session — a decoded default, an enum membership, a class presence, a `case` switch. Strongest tier short of the disassembly spike. |
| **📖** | tutorial-extracted | from the community tutorials/wikis — vocabulary and mechanism are real, but the specific semantics are "leads to confirm," not verified against this build. |
| **decompiled** | disassembly spike | grounded in the CSG/BSP disassembly spike (§4) — read from the compiled instructions and constants (machine code and constant tables, not just string literals), stronger than 📖. |

Scope tags ride alongside: **[ENGINE]** = generic UnrealEngine 1 · **[DX]** = Deus-Ex-specific. Keep
them apart: DX subclasses, presets, and pawn sizes differ from stock UE1, and UT-only
content/gametypes do not transfer.

---

## 2. Sources crawled — with scope (read this before trusting a fact's reach)

| Source | What it is | Scope |
|---|---|---|
| **Steve Tack's Deus Ex Lab** (`stevetack.com/archive/TacksDeusExLab/`, ~65 pages) | The Deus-Ex level-editing tutorial site | **[DX]** |
| **Wolf's Tutorials** (Tony Garcia "Wolf", DX Community-Update GitHub, 14 zips) | Unreal (1998) tutorials — patch 225f / build 220. Engine mechanics carry to DX; all game content (classes/packages) is Unreal's, not DX | **[ENGINE]** (never promote Wolf's package/class names to the DX catalog) |
| **tactical-ops.eu `/info/editor/`** | Large UT99/Unreal editor-tutorial mirror; strong on technique + property names, weak on prescriptive dimensions | [ENGINE] |
| **lodev lighting** (`lodev.org/unrealed/lighting/lighting.html`) | Single-page full light-property reference | [ENGINE] |
| **BeyondUnreal / OldUnreal Legacy wikis** (unrealarchive.org mirrors, Slipyx/UT99) | Human-scale numbers + the BSP-problem corpus | [ENGINE] |
| **Official Deus Ex SDK "Level Design" manual** (scrigroup mirror) | The shipped SDK design/gameplay-wiring reference | **[DX]** |
| **DeusEx `.uc` source** (Deus-Ex-Plus GitHub mirror) | Near-vanilla class source; byte-exact defaults verified against the local `DeusEx.u` | **[DX]** |
| **Spector / Smith immersive-sim talks** (GDC / Gamasutra postmortems, "Rules of Roleplaying", "Systemic Level Design"; wesplays "Spaghetti Level Design") | The design-philosophy doctrine — see [`design-craft.md`](./design-craft.md) | **[DX]** (doctrine) |
| **🔬 the shipped DX packages** — `DX/System/{Engine,DeusEx,Fire}.u`, `DX/Textures/*.utx` | direct greps + uedcli decodes this session | **[DX]** / [ENGINE] (per fact) |
| **The CSG/BSP disassembly spike** ([`../../../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md`](../../../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md)) | decompiled ground truth for the BSP-hole mechanism | [ENGINE] |
| ~~ut99.org file id=14742~~ | **UNRETRIEVABLE** — JS bot-check / 403; coverage overlaps tactical-ops | — |

---

## 3. Binary verifications done directly (🔬, this session)

Facts read straight from the shipped packages — the highest-confidence non-decompiled tier, seeding
the engine-facts regression the measurement spike pins (per the spikes rule).

- **Player / NPC / actor class defaults** — decoded via `actor build <Class> | actor add - | actor
  prop get - <Prop>` from `DeusEx.u`: the JC Denton cylinder (20 × 47.5), Mass 150, `BaseEyeHeight`
  40, `JumpZ` 300, `GroundSpeed` 320, `MaxStepHeight` 25, `AccelRate` 1000; `MJ12Troop` cylinder 20 ×
  47.5, `MaxRange` 1000, `BaseAccuracy` 0.2, `Health` 100; `Engine.Light` defaults (Radius 64 /
  Brightness 64 / Hue 0 / Saturation 255 / LT_Steady / LE_None); `SecurityCamera` cameraFOV 4096 /
  range 1024 / swing 8192; `NanoKey` cylinder 2.05 × 3.11; `ParticleGenerator` defaults. All in
  [`human-scale.md`](./human-scale.md).
- **`LE_Negative` is absent from DeusEx `Engine.u`.** The UT2004-era `LE_Negative` spatial-light
  effect does not exist in the DX `ELightEffect` enum (re-verified against this install's `Engine.u`
  🔬, config `paths` = `/DX/System`); the old lighting guide's doc bug is corrected in
  [`lighting.md`](./lighting.md). The `ELightEffect` enum has 20 members (`LE_None … LE_Unused`, the
  standard UE1 roster including `LE_Shock`/`LE_Disco`/`LE_Shell`/`LE_Rotor`); the only absent value is
  `LE_Negative`. Trap: a `strings`-grep of the name table under-reports enum members — tab-indented
  `\tLE_Foo,` definitions and padded name-table entries slip past a naive grep, which produced the
  bogus "16 members / lacks Shock/Disco/Shell/Rotor" claim. Verify enums with `class show` / `actor
  prop get` (decoder-backed), never `strings`.
- **DX `ELightType` includes `LT_Pulse`/`LT_Blink`** (embedded enum source) — the temporal list is
  correct.
- **DX class catalog confirmed present in `DeusEx.u`** — `DeusExMover, BreakableGlass, BreakableWall,
  ElevatorMover, WaterZone, Keypad1/2/3, HackableDevices, SecurityCamera, AutoTurret, AlarmUnit,
  NanoKey, ScriptedPawn, DataLinkTrigger, AllianceTrigger, PatrolPoint, DeusExLevelInfo,
  ComputerSecurity/Personal/Public, FlagTrigger, GoalCompleteTrigger, LogicTrigger, SequenceTrigger,
  MultiMover, ParticleGenerator, …` — in [`dx-classes.md`](./dx-classes.md) / [`dx-npcs.md`](./dx-npcs.md).
- **`LavaZone` / `PainZone` are not DX classes** (UT-only) — DX does pain via `ZoneInfo bPainZone` +
  `DamagePerSec` + a `DamageType` name.
- **Ladders are texture-driven** — DX has a `case 'Ladder':` group switch; any surface whose texture
  Group is `Ladder` is climbable (built-ins `ladder_a`, `LadrBrwnMetal` in `CoreTexMetal`). No
  actor, no flag. In [`textures.md`](./textures.md).
- **The `Fire.u` fractal-texture family** — `FractalTexture extends Texture`; `FireTexture` (29-value
  `ESpark`, `bRising`, no `FireType`), `WaterTexture` (20-value `WDrop`), `IceTexture`, `WaveTexture`,
  `WetTexture`. `PaletteModifier` does not exist in shipping DX (an OldUnreal-227 addition).
- **DX security-camera monitors do not use `ScriptedTexture`** (no `ScriptedTexture` ref in
  `DeusEx.u`) — the feed renders inside the hackable-computer UI, not on a world surface. In
  [`dx-classes.md`](./dx-classes.md) / [`dx-conversations-computers.md`](./dx-conversations-computers.md).
- **UT `ScriptedPawn` names confirmed absent from DX** — `bFearIndoors/Darkness/Zones`, `HateTag`,
  `HateThreshold`, `IdealRange`, `SeekTag`, `bCanClimb`, `ThingFactory`,
  `AlarmPoint`. (`Aggressiveness` is not truly absent — vanilla `HumanMilitary` lacks it, but the
  UED22 editing package adds a `var() float Aggressiveness`; uedcli accepts it, the shipped game ignores
  it. See the caveat in [`dx-npcs.md`](./dx-npcs.md) §8.) (`AlarmTag` is a real DX `ScriptedPawn` property — `var(Orders) name AlarmTag`;
  `AmbushPoint` exists in `Engine.u` as a stock `NavigationPoint` but DX drives NPCs via
  `ScriptedPawn` orders, not `AmbushPoint`.) In [`dx-npcs.md`](./dx-npcs.md).
- **The 18 `CoreTex*` texture packages present on disk** (Brick … Wood) — in [`textures.md`](./textures.md).

---

## 4. The disassembly spike (decompiled — strongest tier for BSP)

The BSP-hole mechanism is grounded in the CSG/BSP disassembly spike, not tutorials:

> [`../../../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md`](../../../spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md)

It is ground truth wherever tutorials and disassembly disagree, letting [`csg-bsp.md`](./csg-bsp.md)
state the mechanism (discrete numeric-validity tolerance bands — the 0.25 uu split band, the < ~1e-4
uu colinear-collapse, the < 3-vertex / zero-area `FPoly` discard) and reject the false folk
explanation ("floating-point overflow / the engine gives up on the maths"). The engine facts it pins
are re-asserted by committed regressions so a violation trips a red test.

---

## 5. Access notes (for a future crawl pass)

- **stevetack.com** needs `curl --insecure` over HTTP — its TLS cert is for `*.win.arvixe.com` (broken
  chain).
- **ut99.org downloads** are gated behind a crypto-JS bot-check; **file id=14742 could not be
  fetched.** If wanted, supply it directly. Its coverage overlaps the tactical-ops mirror, so the gap
  is small.
- **Class defaults** are read from the substrate with uedcli, not crawled: `actor build <Class> |
  actor add - | actor prop get - <Prop>` (offline, no editor). `class show` gives names/types only.
- **Per-package texture enumeration** comes from the `texture` catalog verb, not tutorial lists.

---

## 6. Residual gaps (none blocking)

Three gaps remain after multiple passes; none blocks authoring:

1. **ut99.org tutorial (id=14742)** — still unretrievable (JS bot-check). Its UT99 content overlaps
   the tactical-ops mirror, so the practical loss is minimal.
2. **Truly `native` C++ class defaults** — a few classes are `native` with empty script
   `defaultproperties`, so their defaults live in compiled C++, not the package — the `Fire.u`
   fractal-texture `FX_*` / `RenderHeat` / `WaveAmp` numeric values are the notable case. These are
   unrecoverable offline. Everything script-defaulted (actors, pawns, lights, movers, particles,
   decorations, cameras) reads cleanly via uedcli; this gap is confined to the fractal painting
   parameters, a Texture-Browser authoring concern, not level geometry.
3. **Shipped-map architectural dimensions** — the real room/corridor/doorway extents as built in the
   shipped maps (beyond the player-anchored figures in [`human-scale.md`](./human-scale.md)) are
   properties of map geometry, not class defaults, so they are the one genuinely editor-bound
   measurement: a one-time editor `MAP EXPORT` of a handful of shipped `DX/Maps/*.dx` into a T3D
   corpus, then model-side measurement (`actor bbox`, `brush poly list`, `PlayerStart` `Location`s).
   This is the B2 half of the human-scale measurement spike; the offline B1 half (class-default
   anchors) is already done inline (see gap 2 and [`human-scale.md`](./human-scale.md) §8).

**Net:** remaining specifics are read from the substrate with uedcli (defaults, texture catalog) or
pinned by the spike's B2 map-export corpus — not found by more reading.

---

*Siblings: [`README.md`](./README.md) (index) · [`human-scale.md`](./human-scale.md) ·
[`design-craft.md`](./design-craft.md) · [`csg-bsp.md`](./csg-bsp.md) · [`textures.md`](./textures.md) ·
[`dx-classes.md`](./dx-classes.md) · [`dx-npcs.md`](./dx-npcs.md).*
