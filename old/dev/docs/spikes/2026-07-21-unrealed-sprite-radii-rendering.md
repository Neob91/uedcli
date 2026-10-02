# Spike: how UnrealEd (UE1) renders sprites, radii, and light/sound reach

**Date:** 2026-07-21
**Question:** How does the original UnrealEd (UnrealEngine 1, ~1998-2000; Unreal / UT /
Deus Ex) draw non-mesh actors as sprites, draw the collision-radii overlay, and convert
the byte `LightRadius` / `SoundRadius` to world units — so our offline Python renderer can
match it.

**Primary evidence:** the **UnrealEngine 1 v200 retail source** (`PACKAGE_FILE_VERSION 61`,
the same package lineage as Deus Ex), cloned from the `fgsfdsfgs/UE1` GitHub mirror
(<https://github.com/fgsfdsfgs/UE1>). Where a fact is quoted below as "v200 source" it was
read directly from that tree; the exact file/line is cited. Wiki/forum claims are cross-checked
against the source and any conflicts are called out.

Confidence markers (per repo convention): ✅ = live/source-verified, 🔬 = probed, 📖 = inferred
from docs.

---

## Formulas to use (summary)

| Quantity | Formula (world units, "UU") | Confidence |
|--------------------------|------------------------------------------------------------------|---|
| Light reach radius | `WorldLightRadius = 25.0 * (LightRadius + 1)` | ✅ source |
| Sound reach radius | `WorldSoundRadius = 25.0 * (SoundRadius + 1)` | ✅ source |
| Volumetric-light radius | `WorldVolumetricRadius = 25.0 * (VolumeRadius + 1)` | ✅ source |
| Sprite world width | `DrawScale * Texture.USize` (1 texel = 1 UU at DrawScale=1) | ✅ source |
| Sprite world height | `DrawScale * Texture.VSize` | ✅ source |
| Collision cylinder radius| `CollisionRadius` (UU, as-is) | ✅ source |
| Collision cylinder height| total height `= 2 * CollisionHeight` (`CollisionHeight` is HALF) | ✅ source |

Key gotchas, all detailed below:
- `LightRadius`, `SoundRadius`, `VolumeRadius` are **bytes (0-255)**, not UU and not floats, in UE1.
  The `+1` inside the formula is real — do not drop it. `LightRadius=0` still reaches 25 UU.
- The sprite drawn is the actor's **`Texture`** property (default `S_Actor`), **not** the
  separate `Sprite` property, in the v200 software renderer.
- In the **editor icon overlay** path (`SHOW_ActorIcons`), `DrawScale` is **forced to 1.0** — so
  editor icons ignore `DrawScale`. A genuine in-game `DT_Sprite` actor *does* honor `DrawScale`.
- The radii overlay in v200 draws **only in the orthographic (2-D) viewports, only for
  selected actors.** The 3-D perspective wire-cylinder was added by a **later UT patch** — see Q2.

---

## Q1 — Sprite size in the editor

### What is drawn
A non-mesh actor with `DrawType==DT_Sprite` (Lights, Triggers, PathNodes, Keypoints, …) is drawn
as a screen-facing 2-D bitmap of the actor's **`Texture`** property.

- `Engine/Classes/Actor.uc` declares both `var(Display) texture Sprite;` (comment: "Sprite
  texture if DrawType=DT_Sprite") and `var(Display) texture Texture;` (comment: "Misc texture"),
  and its `defaultproperties` set `DrawType=DT_Sprite`, `Texture=S_Actor`, `DrawScale=1.0`. So the
  base class's editor icon is `S_Actor` (imported at the top of `Actor.uc`:
  `#exec Texture Import File=Textures\S_Actor.pcx Name=S_Actor`). Subclasses override `Texture`
  with their own icon (`S_Light`, `S_Trigger`, …). ✅ source (`Actor.uc:155-183, 882-884`)
- **Despite the `Sprite` var's comment, the v200 software renderer draws `Actor->Texture`, not
  `Actor->Sprite`.** `FDynamicSprite::Setup` uses `UTexture* Texture = Actor->Texture;` and the
  perspective path uses `Sprite->Actor->Texture`. The `Sprite` var is only referenced for
  network replication in `Actor.uc`. So for rendering purposes, read `Texture`. ✅ source
  (`Render/Src/UnSprite.cpp:176, 701-706`; `Actor.uc:566-567`)

### How big it is drawn
From `FDynamicSprite::Setup` (`Render/Src/UnSprite.cpp:194-221`):

```cpp
GRender->Project( Frame, Actor->Location, ScreenX, ScreenY, &Persp );
FLOAT XSize = Persp * DrawScale * Texture->USize;   // screen-space width  in pixels
FLOAT YSize = Persp * DrawScale * Texture->VSize;   // screen-space height in pixels
X1 = ScreenX - XSize/2;  X2 = ScreenX + XSize/2;    // centered on the actor origin
```

`Persp` is the projection scale returned by `URender::Project` (`Render/Src/UnSoftLn.cpp:166`):
- **Orthographic views:** `Persp = Frame->RZoom` — the view's screen-pixels-per-world-unit zoom.
- **Perspective view:** `Persp = Frame->Proj.Z / Z` — the standard `focal / depth` factor
  (pixels per world unit at that depth).

Either way `Persp` converts world units → screen pixels, so factoring it out gives the sprite's
**world-space** footprint:

> **sprite world width = `DrawScale * USize`, sprite world height = `DrawScale * VSize`.**
> i.e. **1 texture texel = 1 world unit at `DrawScale = 1`**, and the bitmap is centered on the
> actor's `Location`, always axis-aligned to the screen (billboard). ✅ source

So yes — a sprite **scales linearly with `DrawScale`**, and the base size is the texture's own
`USize`×`VSize` in texels mapped 1:1 to world units. There is no separate "sprite base size"
constant; it is the texture's pixel dimensions. (Editor icon PCXs like `S_Actor` are small, on
the order of tens of texels, so they occupy tens of UU on-screen at DrawScale 1.)

### Editor-icon caveat (important)
The same `Setup` also runs when the viewport has the `SHOW_ActorIcons` flag (so that
mesh/brush actors still get a clickable icon). In **that** branch the code overrides:

```cpp
if( Frame->Viewport->Actor->ShowFlags & SHOW_ActorIcons ) {
    DrawScale = 1.0;                                   // <-- DrawScale forced to 1
    if( !Texture ) Texture = GetDefault<AActor>()->Texture;   // fall back to S_Actor
}
```

So **when the editor is showing actor icons, `DrawScale` is ignored (treated as 1.0).** A
genuine `DT_Sprite` actor rendered *without* `SHOW_ActorIcons` (e.g. in-game, or a pure sprite
view) honors its real `DrawScale`. For matching the editor's icon overlay specifically, use
`DrawScale = 1`. ✅ source (`Render/Src/UnSprite.cpp:180-184`)

**Sources:** UE1 v200 source `Actor.uc`, `UnSprite.cpp`, `UnSoftLn.cpp`
(<https://github.com/fgsfdsfgs/UE1>); BeyondUnreal wiki *Actor/Display*
(<https://beyondunrealwiki.github.io/pages/actor-display.html>) confirms "DT_Sprite … displays a
sprite with the material set in the Texture property" and "DrawScale scales the actor's visual
representation" (📖, consistent with source).

---

## Q2 — The radii view (Actor Radii / `SHOW_ActorRadii`)

The flag is `SHOW_ActorRadii = 0x00000002` ("Show actor collision radii",
`Engine/Inc/UnCamera.h:120`). ✅ source

### What v200 actually draws
All radii drawing lives in one block in `Editor/Src/UnEdCam.cpp:1537-1573`. The **guard** is:

```cpp
if( Viewport->IsOrtho()                              // ORTHO viewports only
    && (Viewport->Actor->ShowFlags & SHOW_ActorRadii)
    && Actor->bSelected )                            // SELECTED actors only
```

Inside, for a non-brush actor:

```cpp
// Collision radius — TOP view only, as a CIRCLE:
if( Actor->bCollideActors && RendMap==REN_OrthXY )
    Render->DrawCircle( Frame, C_ActorArrow, LINE_None, Actor->Location, Actor->CollisionRadius );

// Collision height — FRONT/SIDE views, as a BOX (rectangle):
FVector Ext( CollisionRadius, CollisionRadius, CollisionHeight );
FVector Min = Location - Ext,  Max = Location + Ext;
if( Actor->bCollideActors && RendMap!=REN_OrthXY )
    Render->DrawBox( Frame, C_ActorArrow, LINE_Transparent, Min, Max );

// Light reach — CIRCLE (any ortho view):
if( LightType!=LT_None && LightBrightness && LightRadius )
    Render->DrawCircle( Frame, C_ActorArrow,      LINE_None, Location, Actor->WorldLightRadius() );

// Volumetric reach — CIRCLE:
if( LightType!=LT_None && VolumeBrightness && VolumeRadius )
    Render->DrawCircle( Frame, C_Mover,           LINE_None, Location, Actor->WorldVolumetricRadius() );

// Sound reach — CIRCLE:
if( Actor->AmbientSound )
    Render->DrawCircle( Frame, C_GroundHighlight, LINE_None, Location, Actor->WorldSoundRadius() );
```

Confirmed facts:
- **Collision radius → circle in the TOP (`REN_OrthXY`) view**, radius = `CollisionRadius`. ✅
- **Collision height → rectangle (box) in the FRONT/SIDE views**, with half-extents
  `(CollisionRadius, CollisionRadius, CollisionHeight)` — so on screen it is
  `2*CollisionRadius` wide × `2*CollisionHeight` tall. ✅
- **`CollisionHeight` is a HALF-height** — the box spans `Location.Z ± CollisionHeight`, total
  height `2*CollisionHeight`. This also matches `Actor.uc:246` comment "Half-height cyllinder"
  and the default `CollisionRadius=22, CollisionHeight=22`. ✅ source
- The cylinder is built from **world axes** (`Ext` is an axis-aligned vector, and the circle is
  centered on `Location`), so it is **always upright / axis-aligned and does NOT rotate with the
  actor's `Rotation`.** ✅ source (matches BeyondUnreal wiki *Collision Cylinder*: "always upright,
  no matter what the actor's orientation").
- Light/volumetric/sound reach are drawn as **circles** using the `WorldLightRadius()` /
  `WorldVolumetricRadius()` / `WorldSoundRadius()` conversions (see Q3) — and, unlike the
  collision circle, with **no `RendMap` guard**, so they draw a circle in *all three* ortho views
  (the reach is spherical). ✅ source

### Colors (v200 defaults, from `Engine/Config/Default.ini`)
These are `EditorEngine` config colors, so they are user-overridable, but the shipped defaults are:

| Overlay | Color constant | Default RGB | Appearance |
|--------------------|-------------------|-------------------|---|
| Collision cyl. | `C_ActorArrow` | `(163, 0, 0)` | dark red |
| Light reach | `C_ActorArrow` | `(163, 0, 0)` | dark red |
| Volumetric reach | `C_Mover` | `(255, 0, 255)` | magenta |
| Sound reach | `C_GroundHighlight`| `(0, 0, 127)` | dark blue |

✅ source (`Engine/Config/Default.ini:547-566`, `Editor/Classes/EditorEngine.uc:78-107`).
Line style in ortho: circles use `LINE_None` (solid), the collision box uses `LINE_Transparent`.

> **Conflict noted:** the BeyondUnreal wiki *Actor/Lighting* page says the **light** reach shows
> as a "dark blue circle." The v200 source says light reach is `C_ActorArrow` = **dark red**, and
> it is the **sound** reach that is dark blue (`C_GroundHighlight`). The wiki likely conflated the
> two (or a later build/ini remapped colors). Trust the source: light = dark red, sound = dark blue
> **in v200 defaults**; but since these are `.ini` config values, a given install can differ.

### Version conflict: 2-D only vs 3-D cylinder
The BeyondUnreal wiki *Collision Cylinder* page describes the radii overlay as a **"cylinder made
of dotted red lines"** in the 3-D (perspective) viewport, a circle in top, a rectangle in
front/side. The **v200 source draws radii in ORTHO viewports only** (the `Viewport->IsOrtho()`
guard) — there is **no perspective cylinder** in v200.

This is a genuine **engine-version difference**, and it is resolved by the **Unreal Tournament
patch release notes**, which list as a *new* feature:

> "Radii view will now work in the 3D window by rendering the collision cylinder as an 8-sided
> wire cylinder, and will also show the radius of things like lights in the 3D window."
> — UT release notes (<http://utgl.unrealadmin.org/Patch/ReleaseNotes.htm>, via search snippet;
> the page's TLS cert is expired so it was read through the search index, ⚠️ verify wording if
> it matters).

So: **v200 (early Unreal) = ortho-only radii; later UT/UnrealEd 2.x builds added an 8-sided wire
cylinder in the perspective view.** Deus Ex ships UnrealEd 2.x (build ~1112), so the Deus Ex
editor most likely shows the 3-D wire cylinder too — but that specific behavior is **not**
verifiable from the v200 tree; treat the perspective cylinder as 🔬 (wiki + patch notes) and the
ortho circle/rectangle as ✅ (v200 source, and unchanged in later builds).

**Sources:** UE1 v200 `UnEdCam.cpp`, `UnCamera.h`, `Default.ini`, `EditorEngine.uc`
(<https://github.com/fgsfdsfgs/UE1>); BeyondUnreal wiki *Collision Cylinder*
(<https://beyondunrealwiki.github.io/pages/collision-cylinder.html>); UT release notes
(<http://utgl.unrealadmin.org/Patch/ReleaseNotes.htm>); BeyondUnreal wiki *UnrealEd Viewport*
(<https://beyondunrealwiki.github.io/pages/unrealed-viewport.html>) for the Actors → Radii View menu.

---

## Q3 — `LightRadius` / `SoundRadius` → world units

`LightRadius`, `SoundRadius`, and `VolumeRadius` are all **`byte` (0-255)** in UE1
(`Actor.uc:210` `var(Sound) byte SoundRadius;`, `Actor.uc:304-311` `var(Lighting) byte
LightRadius, …, VolumeRadius, …;`). Default `SoundRadius=32`; `LightRadius` has no default (0).
✅ source

The **exact** conversion to world units is a set of inline engine methods
(`Engine/Inc/AActor.h:21-23`):

```cpp
FLOAT WorldLightRadius()      const { return 25.0 * ((int)LightRadius  + 1); }
FLOAT WorldSoundRadius()      const { return 25.0 * ((int)SoundRadius   + 1); }
FLOAT WorldVolumetricRadius() const { return 25.0 * ((int)VolumeRadius + 1); }
```

So:

> **`WorldLightRadius = 25 * (LightRadius + 1)` UU** — e.g. `LightRadius=8` → 225 UU;
> `LightRadius=0` → 25 UU; `LightRadius=255` → 6400 UU.
> **`WorldSoundRadius = 25 * (SoundRadius + 1)` UU** — e.g. the default `SoundRadius=32` → 825 UU.

These same methods feed both the actual lighting math (`Render/Src/UnLight.cpp:1392, 1436, 2097`
compute `Radius = Actor->WorldLightRadius()` for attenuation) and the editor's radius circle
(`UnEdCam.cpp` above). So **what UnrealEd draws == what the light actually reaches** — the circle
is exact, not decorative. ✅ source

**Resolving the "×25" vs "×27" claims:**
- The commonly-cited **"`LightRadius * 25`"** is essentially correct but **drops the `+1`**. The
  true formula is `25 * (LightRadius + 1)`. For large radii the `+1` is negligible; for small
  ones it is not (and it means the minimum non-zero reach is 25 UU, and `LightRadius=0` is *not*
  zero reach). Use the `+1` form.
- The BeyondUnreal wiki *Actor/Lighting* page's **"factor of about 27"** is an empirical
  eyeball estimate ("There seems to be a factor of about 27 …"), and that page treats
  `LightRadius` as a **float** (`float LightRadius`) — i.e. it is describing a **UE2** engine
  (UT2003/UnrealEd 3), where the property changed type. It does **not** apply to UE1. For UE1 the
  source-exact factor is 25 (with `+1`). ⚠️ conflict resolved in favor of source.

**Sources:** UE1 v200 `Engine/Inc/AActor.h`, `Actor.uc`, `UnLight.cpp`, `UnEdCam.cpp`
(<https://github.com/fgsfdsfgs/UE1>); BeyondUnreal wiki *Actor/Lighting*
(<https://beyondunrealwiki.github.io/pages/actor-lighting.html>) — the "~27" / float claim, which
is UE2-era, not UE1; BeyondUnreal *General Scale and Dimensions*
(<https://unrealarchive.org/wikis/unreal-wiki/Legacy:General_Scale_And_Dimensions.html>) notes
light/sound radii "have a set range you can't change" (i.e. the 0-255 byte), consistent with source.

---

## Q4 — Screenshots of the viewports

I could not retrieve an inline image file, but the following pages host/describe the relevant
overlays (their prose descriptions match the v200 source above):

- **BeyondUnreal wiki — Collision Cylinder**
  (<https://beyondunrealwiki.github.io/pages/collision-cylinder.html>): describes/illustrates the
  overlay as a **circle in the top 2-D view, a rectangle in front/side views, and a dotted-red
  wire cylinder in the 3-D view**, and states the cylinder "is always upright, no matter what the
  actor's orientation." (📖 — matches source, except the 3-D cylinder is a later-build feature.)
- **BeyondUnreal wiki — UnrealEd Viewport**
  (<https://beyondunrealwiki.github.io/pages/unrealed-viewport.html>): documents the *Viewport
  Caption Context Menu → Actors → Radii View* toggle that enables the overlay (per-viewport).
- **BeyondUnreal wiki — Actor/Lighting**
  (<https://beyondunrealwiki.github.io/pages/actor-lighting.html>): describes selecting a light and
  reading its reach off the drawn radius circle in an ortho viewport.
- **OldUnreal "Hunting hidden actors" thread**
  (<https://www.oldunreal.com/phpBB3/viewtopic.php?t=3765>): community screenshots of actor
  sprites/icons in UnrealEd viewports (useful reference for icon appearance/scale). (📖)

If a pixel-accurate icon size is needed later, the last unknown is the actual `USize`×`VSize` of
the editor icon PCXs (`S_Actor`, `S_Light`, `S_Trigger`, …); those live in the game's editor
`.utx`/imported textures, not in the source tree, and would be read straight from the package.

---

## Regression-test candidates (per the "pin the finding" rule)

The three world-radius conversions and the half-height convention are **checkable engine facts**
and should get a committed assertion (e.g. in a `test_engine_facts`-style module) if uedcli ever
computes them:

- `world_light_radius(0) == 25`, `world_light_radius(8) == 225`, `world_light_radius(255) == 6400`.
- `world_sound_radius(32) == 825`.
- collision box total height `== 2 * CollisionHeight`; box half-width `== CollisionRadius`.
- sprite world footprint `== (DrawScale*USize, DrawScale*VSize)`, and `DrawScale`-forced-to-1 under
  the icon path.

These re-assert the `25*(x+1)` / half-height / 1-texel-per-UU rules so a later change can't
silently drift from UnrealEd's behavior.
