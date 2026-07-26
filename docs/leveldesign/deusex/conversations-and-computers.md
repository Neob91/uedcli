# Conversations, computers & datacubes  [DX]

Deus Ex tells its story through **conversations** (NPC dialogue), **computers** (email, bulletins,
security), and **datacubes** (readable text that lands in the player's Notes). This guide is a
**user-level overview** of how a level *wires* to that content. The full authoring pipeline — writing
conversations in the external **ConEdit** tool, compiling text packages with `ucc make` — is
mission-scripting work outside the scope of these user guides; it is not covered here.

---

## Conversations

A conversation is owned by a character and triggered when the player interacts with them.

- **Binding.** Each `ScriptedPawn` carries a **`BindName`** (spaces-free — the player's is `JCDenton`).
  The conversation system and the flag database key off this name, so an NPC that talks needs one set
  (see [`npcs.md`](npcs.md)).
- **Level binding.** The map's `DeusExLevelInfo` names the compiled **`ConversationPackage`** and a
  **`missionNumber`**; the mission number must match the one the conversation was authored for, or its
  state won't bind.
- **Invocation modes** — how a conversation starts:
  - *PC Frobs NPC* — the player walks up and uses the character. (Reliable.)
  - *NPC Enters PC Radius* — starts when the NPC comes within a set radius of the player. (Reliable.)
  - *Player Bumps NPC* — present in ConEdit, but in shipped DX it behaves **just like *PC Frobs NPC***
    (the separate "seeing" trigger was never implemented) — so Frob and Radius are the two real modes.

- **InfoLink / Datalink.** In-game radio-style briefings ("InfoLink") are the **`DataLinkTrigger`** class
  — place one, set its **`datalinkTag`** to the datalink conversation to play, and let the player Touch
  it (or fire it via `Tag`/`Event`). Without `datalinkTag` set, nothing plays.

From the level author's seat, your job is: set `BindName`s on the NPCs, point `DeusExLevelInfo` at the
conversation package, place `DataLinkTrigger`s where briefings should fire, and let the ConEdit-authored
content bind to those names. The actual dialogue trees are authored outside uedcli.

## Computers

Computers are placed actors the player hacks or logs into. Three kinds:

- **`ComputerPersonal`** — email terminals (accounts, inboxes, message files).
- **`ComputerPublic`** — public terminals showing bulletins/notices.
- **`ComputerSecurity`** — the security console. Its **`Views[i]`** entries wire live camera feeds and
  device control: `cameraTag` (which `SecurityCamera` to show), plus optional `turretTag` and `doorTag`
  so a hacker can slew turrets and open doors. See [`gameplay-wiring.md`](gameplay-wiring.md) for the
  camera→computer recipe — the feed renders inside this UI, never on a world monitor.

The account/email/bulletin *text* is authored as external text files compiled into the mission's
packages (dev-KB territory); the level author places the computer and sets its tags and login details.

## Datacubes and readable info devices

DataCubes, books, and newspapers are **`DeusExDecoration`** info devices (see [`classes.md`](classes.md)).
The key user-facing fact:

- A DataCube's **`textTag`** / **`TextPackage`** names the text it displays, and **reading a DataCube
  writes its text into the player's Notes** — so it's the primary channel for environmental
  storytelling *and* for handing out door codes and hints that reward exploration.

Place a datacube near what it's about, point its `textTag` at the authored text, and it becomes a
persistent note the player can re-read. (The text markup — `<P>`, `<COMMENT>`, datacube colour/centre
tags — and how the text packages are built are part of the external text-authoring pipeline, outside
the scope of these user guides.)

---

## See also

- [`classes.md`](classes.md) — `DeusExLevelInfo`, computers, datacube decorations.
- [`npcs.md`](npcs.md) — `BindName` and giving NPCs dialogue.
- [`gameplay-wiring.md`](gameplay-wiring.md) — `DataLinkTrigger`, camera feeds, flags for story state.
- [`design-philosophy.md`](design-philosophy.md) — environmental storytelling as a design principle.
