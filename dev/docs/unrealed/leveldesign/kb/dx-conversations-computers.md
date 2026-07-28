# DX conversations, computers & info devices  [DX]

The DX-specific information layer: spoken conversations (ConEdit), the in-world
computers (email/bulletin/security terminals), the readable info devices
(DataCubes/books/newspapers), and the `ScriptedTexture` "draw-on" surface — plus
how DX security-camera monitors actually render (not a camera feed painted on a
wall).

This edges from level design into mission scripting; wiring a level's story,
door codes and security terminals is part of authoring a DX level. Everything
marked ✅🔬 / ⟨bin⟩ was verified against the shipped `DX/System/{Engine,DeusEx}.u`
this session.

> **Siblings.** [`dx-classes.md`](dx-classes.md) (the trigger/flag/goal actors that
> conversations and computers hook into) · [`dx-npcs.md`](dx-npcs.md) (NPC
> `BindName`, `ConvOrders`) · [`asset-pipeline.md`](asset-pipeline.md) (`ucc make`,
> importing text/image packages). Full compiled reference:
> [`README.md`](README.md).

Markers: `[DX]` throughout unless flagged `[ENGINE]`. ✅🔬/⟨bin⟩ = binary-verified;
📖 = DX SDK manual / tutorial corpus.

---

## 1. Conversations (ConEdit)  [DX] 📖

Conversations are authored in an external tool, ConEdit (not UnrealEd, not
uedcli), and compiled into packages.

**Build pipeline.** `ucc make` compiles a conversation package into three `.u`
files:
- `Pkg.u` — the conversation logic
- `PkgText.u` — the text (post-Mar-2001 SDK: build your text into your own
  package rather than overwriting `DeusExText.u`)
- `PkgAudioMissionNN.u` — the voice audio for mission NN

**Binding a conversation to a character.** The conversation's owner is a
character's `BindName` (no spaces; the player is `JCDenton`). The level binds via
`DeusExLevelInfo.ConversationPackage` + `missionNumber` — the `missionNumber` on
the level must match the conversation's mission number. (Stock DX missions are
~1–15; 16–97 is the convention for custom/fan missions, not a required range.)
See `DeusExLevelInfo` in [`dx-classes.md`](dx-classes.md) §6 and the NPC
`BindName` in [`dx-npcs.md`](dx-npcs.md) §5.

**Invocation modes** (how a conversation starts):
- "PC Frobs NPC" — player uses/frobs the NPC. (Reliable.)
- "NPC Enters PC Radius" — proximity trigger (radius in uu). (Reliable.)
- "Player Bumps NPC" — present in ConEdit, but in shipped DX it was hard-wired to
  behave exactly like "PC Frobs NPC", and a separate "seeing" trigger was never
  implemented — so in practice Frob and Radius are the only two real modes.

**InfoLink / Datalink.** The in-game "InfoLink" radio messages are class
`DataLinkTrigger` (place it, tag it, trigger it to play a datalink). Datalink
status is set by the "Datalink Conversation" option (a radio button, Options tab)
+ "Display only once" in ConEdit. By convention a datalink conversation's name
carries a `DL_` prefix, but that is a naming convention only — not mandatory, and
not a required filename prefix. Imported via `#exec CONVERSATION IMPORT`,
compiled with `ucc make`.

Reprogramming an NPC from a conversation uses `ConvOrders` / `ConvOrderTag`
(applied when the convo ends) — see [`dx-npcs.md`](dx-npcs.md) §1.

```
# place an InfoLink trigger; datalinkTag names the datalink CONVERSATION to play (Touch fires it)
actor build DeusEx.DataLinkTrigger --prop datalinkTag=DL_intro --at 128,128,32 | actor add -
```

---

## 2. Computers  [DX] 📖 ✅🔬

Three placeable computer classes, all `Computers` descendants (under
`ElectronicDevices`). `HackableDevices` is a sibling branch under
`ElectronicDevices` — a computer is not a `HackableDevices`; it's protected by
login accounts + `lockoutDelay`, not the multitool `hackStrength`:

| Class | Role | Content files |
|---|---|---|
| **`ComputerPersonal`** | email terminal | email `<mission>_Email<NN>.txt`; menu `<mission>_EmailMenu_<user>.txt` |
| **`ComputerPublic`** | public bulletins/ATMs/infokiosks | bulletins `<mission>_Bulletin<NN>.txt`; menu lines |
| **`ComputerSecurity`** | security terminal (camera/turret/door control) | `Views[3]` — see §5 |

**Email format (`ComputerPersonal`).** The menu file lists messages with:
```
<EMAIL=id,Subject,From,To,CC>
```
where `To` must match the account's login for the message to appear.

**Bulletin format (`ComputerPublic`).** The menu file lists files with:
```
<FILE=file,Name>
```

**Accounts & logos.** A computer has up to 8 accounts. Its branding is a
`ComputerNode` logo, chosen from 15 fixed values (`CN_UNATCO`, `CN_MJ12Net`,
`CN_NSF`, `CN_VersaLife`, …); the logo is drawn at 61×61 px
(`winLogo.SetSize(61,61)` 🔬).

**Lockout & unimplemented fields.** `lockoutDelay` (seconds locked out after
failed logins), decoded from `DeusEx.u` 🔬: the `Computers` base default is 30;
`ComputerPersonal` overrides to 60, `ComputerSecurity` to 120, and
`ComputerPublic` keeps the inherited 30 (it sets no override of its own).
`titleString` / `titleTexture` / `nodeName` are documented in the SDK but never
implemented in stock code — setting them does nothing. ✅🔬

```
actor build DeusEx.ComputerPersonal --prop Tag=lab_terminal --at 400,200,48 | actor add -
```

---

## 3. Info devices & DataCubes  [DX] 📖 ✅🔬

Readable world text — `DataCube`, books, newspapers (all `DeusExDecoration`
subclasses; see [`dx-classes.md`](dx-classes.md) §5). Key fields: `textTag`,
`TextPackage`, `imageClass` (there is no inline `Text` property). DataCube text is
copied into the player's Notes, so datacubes are how you deliver door codes and
lore the player will want to re-read.

**Markup** (a small tag language inside the text):
- `<P>` — paragraph break · `<COMMENT>` — a comment (both work everywhere).
- `<DC=r,g,b>` — set text colour · `<JC>` — centre-justify. These two work only in
  the info-device text path (datacubes / books / newspapers), not in
  conversations/computers.
- `<B>` / `<I>` / `<U>` (bold/italic/underline) — never work; don't use them.

**DataVault images.** An image shown in the DataVault must be prepared: source
400×400 → pad to 512×512 → convert to 8-bit → split into four 256×256 tiles
assigned to `imageTextures(0..3)`, with MIPS off. See
[`asset-pipeline.md`](asset-pipeline.md).

```
actor build DeusEx.DataCube --prop textTag=door_code_42 --at 320,120,32 | actor add -
```

---

## 4. `ScriptedTexture` — a draw-on surface, not a camera feed  [ENGINE] ⟨bin⟩

`ScriptedTexture` is frequently mistaken for a camera monitor. It is a
script-drawn texture, not a camera view.

- Class chain: `Bitmap → Texture → ScriptedTexture`.
- Props: `NotifyActor`, `SourceTexture`.
- Each frame the engine resets the texture to `SourceTexture`, then calls
  `NotifyActor.RenderTexture()`, where script draws with `DrawTile` / `DrawText`
  / `DrawColoredText` / `TextSize` / `ReplaceTexture`.
- Renderer-dependent — renders under D3D; software/other renderers vary (a runtime concern, 📖).
- Use cases: scoreboards, counters, tombstones, animated readouts — anything a
  script paints frame-by-frame.

Camera-view-to-surface (`DrawPortal`) is not part of stock DX 1.0. `Engine.u`
exposes a native `DrawPortal`, but `DeusEx.u` never calls it (0 references 🔬) —
so it is not how DX monitors work; do not attribute DX camera monitors to it.
`RenderIteratorClass` is the particle/procedural-geometry hook (DX
`LaserIterator` / `ParticleIterator extends RenderIterator` 🔬), unrelated to
monitors.

---

## 5. DX security-camera monitors — how they actually render  [DX] ⟨bin⟩

There is no `ScriptedTexture` reference in `DeusEx.u` — DX camera monitors do not
use it, and there is no world-mounted monitor surface showing a camera feed.
Instead the feed is a live 3D render composited into the hackable-computer
UWindow UI:

1. Place a `SecurityCamera` and give it a `Tag` (see camera defaults in
   [`dx-classes.md`](dx-classes.md) §3).
2. Place a `ComputerSecurity`.
3. Fill its `Views[3]` array — each entry is
   `struct sViewInfo { titleString; cameraTag; turretTag; doorTag }`. Set
   `Views[i].cameraTag` = the camera's tag (and optionally `turretTag` /
   `doorTag` so that view can also control a turret/door).
4. In-game, hacking/using the terminal opens the console UI, whose
   `winCamera.SetViewportActor(camera)` renders the camera's view live inside the window.
   (`SetWatchActor` is the augmentation-zoom window, not this.)

So the "monitor" is the computer terminal UI, reached by frobbing/hacking the
`ComputerSecurity` — not a screen brush in the world.

```
actor build DeusEx.SecurityCamera --prop Tag=cam_lobby --at 512,512,220 | actor add -
actor build DeusEx.ComputerSecurity --prop Tag=sec_terminal \
  --prop 'Views.0=(cameraTag=cam_lobby)' --at 300,300,48 | actor add -
```

(For more views, repeat with the dot-index form — `Views.1=(cameraTag=…)`, `Views.2=(…)`;
`class show DeusEx.ComputerSecurity` lists the `sViewInfo` fields —
`titleString`/`cameraTag`/`turretTag`/`doorTag`.)
