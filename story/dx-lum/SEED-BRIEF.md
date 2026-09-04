# DX_LUM — story exploration seed brief (canon-grounded)

A round of parallel story development for **DX_LUM**, a Deus Ex–like immersive-sim. Five writers each
develop the existing story bible into a complete, long story; six analysts then mine all five for the
strongest twists.

## Canon source — READ IT FIRST

The real story bible lives in a separate cloned repo. Before writing, READ these files in full:

- `/workspace/dx_lum/DevDocs/Story/Overview.md` — the spine (world, factions, the central secret).
- `/workspace/dx_lum/DevDocs/Story/Scenes/Prologue.md` — FMA HQ → outpost → Quinmore.
- `/workspace/dx_lum/DevDocs/Story/Scenes/QuinmoreArrival.md` — arrival, reactor, missing-kid, Harmon.
- `/workspace/dx_lum/DevDocs/Story/Locations.md`, `Ideas.md`, `CityName.md`, `Prompts-For-LLM.md`.

`DevDocs/Story_Old/` is SUPERSEDED — ignore it (its "satellite network" premise is replaced by the
multiverse energy-siphon below).

This brief distills the canon; the files above are authoritative. **Do not contradict canon** — build
ON it. Invent freely in the gaps (new missions, characters, factions, and especially new twists), but
keep the established facts intact.

## The canon (established — keep intact)

- **Genre / feel.** Near-future dystopia (2000–2100), aesthetic close to the original Deus Ex (2000):
  not shiny-futuristic. Immersive sim — branching approaches (stealth / combat / hacking / social),
  infolink messages, player choice. Corporations are greedy and don't care about people; the world is
  rife with black markets, smuggling, syndicates; some corps deal with them.
- **Protagonist: Liam Ryker.** A deliberately blank-slate player-avatar in the JC Denton / Adam Jensen
  mold — low affect, ex-military, elite mercenary/tactician. Leans good but "morally flexible" (ends
  justify the means / just business). An outsider in Quinmore with no cover and no local contacts; the
  player learns the world as he does.
- **The FMA (Federated Multiversal Authority).** Ryker's employer. Across many parallel Earths,
  some develop tech to travel between universes; most of those banded into the FMA to police
  inter-universal travel and punish inter-universe crime. The FMA detects a faint, unprecedented
  **transversal anomaly** from universe **U-7134** and sends Ryker in covertly to investigate.
- **The world: U-7134 / Quinmore.** A former US city (codename **Quinmore**; rename candidates
  **Umbermont / Umberbourne / Umbermere / Umberhaven**). A devastating global war ended in
  continent-scale chemical warfare that made Earth's whole atmosphere lethal (illness in hours, death
  in weeks). Survivors live in sealed, filtered **dome sectors**. Lose power → seals fail → toxic air
  floods in (time to evacuate, then uninhabitable).
- **The Corporate Union (CU).** After the war the megacorps built the domes ("your governments
  couldn't keep you alive, we can") and became the de facto global state — a board of corporate
  reps, no civilian government. City services split by corp: **Nuradyne** = power; **Atlas
  Subsystems** = dome shielding; others = transit/housing/comms. Each corp has legal authority (and
  its own security) over its own infrastructure and can cordon its own "crime scenes."
- **The central secret.** Nuradyne's reactors are **multiversal** — they run by **siphoning energy
  from other universes**, which devastates the drained universes. Only Nuradyne's inner circle knows;
  the CU board approved them as mere "cutting-edge energy tech." The faint anomaly the FMA detected is
  the siphon, NOT travel.
- **The inciting incident.** One drained universe traced the siphon to U-7134 and sent a force-field
  **operative** through the reactor's aperture; the operative caused the slum-district reactor to
  explode, killed Nuradyne security, and fled into the slums. The blast killed Atlas's dome shielding
  (and its fried backup); toxic air flooded the sector. Nuradyne frames it as a **terrorist attack**,
  cordons the district, and screens every evacuee at checkpoints — publicly to find "the bomber,"
  actually to find the operative. Evacuees are dumped in an overcrowded corporate relocation warehouse.
- **The stranded liaison.** Pre-war the FMA had a liaison agent in U-7134. When the war killed his
  government contacts he was stranded (no portal home). Over years he traded FMA / multiversal
  knowledge to Nuradyne for protection — that knowledge is HOW Nuradyne built the siphon reactors.
  Once their engineers no longer needed him, Nuradyne cut him loose (didn't kill him — too much
  paperwork, and nobody would believe him). He's now a broken, bitter, terrified man in Quinmore's
  slums. The FMA believes him dead and has no idea Nuradyne knows anything about the FMA or the
  multiverse.
- **The hinted twist (canon invites it).** The bible explicitly wants twists and asks: *does the FMA
  itself have a hidden agenda beyond what Ryker's been told?* Lean into this.
- **Androids.** Optional flavor: non-organic servants exist; per the owner they do NOT revolt or crave
  freedom. Use for texture, not a robot-uprising plot.
- **Known characters.** Ryker; **Director Harmon** (head of Nuradyne's reactor project — stonewalls
  Ryker, suppressed the abnormal-reactor reports); **Kira Voight** (Nuradyne Chief of Security);
  Ryker's FMA **partner** (stays at the outpost, feeds objectives via infolink); a **slum mother**
  whose **missing son** was detained by Nuradyne security and overheard something he shouldn't have.
- **Player-verb constraints (hard rules from `Prompts-For-LLM.md`).** The PLAYER cannot: review
  surveillance tapes, or hack for "inconsistent timestamps" (NPCs do that off-screen). The player CAN:
  start conversations (explicitly or by entering an area), receive one-way infolink messages, kill/
  incapacitate, bypass doors with multitools, and read computers (an email can trigger an ally
  infolink + the next objective). Design reveals around these verbs, not forbidden ones.

## Established opening beats (honor these; extend past them)

Prologue at FMA HQ (recall, briefing, medical, armory, optional orientation) → portal to the cloaked
U-7134 outpost with a partner → partner triangulates residual energy to the Quinmore slum reactor →
cloaked aircraft to **Northgate** → train downtown. In Quinmore the slum reactor has already exploded
and is cordoned; Ryker infiltrates Nuradyne (forged credentials / hacking / social engineering).
Reactor site: erased logs, dead security; a **datacube** from a dead scientist names **Director
Harmon** and "abnormal reactor readings" → find Harmon. The **missing kid** is found mid-investigation
in a Nuradyne holding cell, having overheard something. `Ideas.md` proposes reusing an "Aire Gardens"
train-station/elevator level down to a subway.

## What each writer must deliver

A **complete, LONG** story document that develops this canon end-to-end. Not an outline — a
fleshed-out narrative. Include:

1. **Logline** + how your version reads.
2. **What you take as fixed vs. what you invented** — a short note so the reader can see your additions.
3. **Full plot, mission by mission**, from the established prologue through a full second and third act
   to your endings. Actually tell the story: what Ryker learns, in what order, who betrays whom, how
   the operative / liaison / Harmon / Voight / the missing kid / the drained universe(s) / the FMA's
   own agenda all pay off. This is the core — make it long and specific.
4. **Factions & power structure** — Nuradyne, Atlas, the CU board, the slums/syndicates, the FMA, the
   drained universe(s); give them conflicting agendas.
5. **Key characters** — extend the known cast and add allies/antagonists/ambiguous figures with motives
   and secrets.
6. **The central twist(s)** — call them out explicitly and land them. At least one should exploit the
   "FMA has a hidden agenda" invitation, and at least one the multiverse-siphon horror. Make them
   playable within the player-verb constraints above.
7. **Player-choice structure & endings** — 2–4 distinct, ideological Deus Ex–style endings.
8. **Themes.**

Diversity across the five is wanted — different twists, different emphases (the operative's universe;
the liaison; the FMA's agenda; the corporate war between Nuradyne and Atlas; the human cost in the
slums). Do not converge. Keep it inside canon.
