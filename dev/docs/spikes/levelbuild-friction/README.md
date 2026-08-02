# uedcli friction log — building three levels with LLM agents

**Date:** 2026-07-25/26 · **Status:** durable evidence, not a plan

Three Claude subagents each built a detailed Deus Ex level from a reference photo
(`ContainerYard`, `TubePlatform`, `DiveBar`) using only the `uedcli` CLI and the
user-facing docs, plus a fourth agent spiking headless materialization. This file
records **every problem, defect, and misunderstanding they hit**, so uedcli can be
improved against real usage rather than guesses.

**Two logs, two axes.** This file and [`agent-reports.md`](agent-reports.md) record **tool friction** —
what blocked the agents *while building*. [`owner-reports.md`](owner-reports.md) records the other
half: **what came out wrong in the finished levels**, judged by the owner playing and inspecting them.
The lists barely overlap, and that is the point — an agent cannot report a defect it never noticed, and
every level here was declared finished, screenshotted and accepted with the owner's findings already in
it. Read both before deciding what to fix: the agent log skews toward missing verbs, the owner log
toward missing *checks*.

This is the first time uedcli has been driven end-to-end, at length, by agents who
started with **no prior knowledge of the tool** — which is exactly its intended user.
That makes the misunderstandings as valuable as the defects: where a competent reader
of the docs still guessed wrong, the tool or the docs are at fault, not the reader.

## How this was gathered

- Direct observation by the orchestrating session.
- **Mined from the seven subagent transcripts** (~53 MB of JSONL) with
  `mine.py` (committed beside this file), which extracts CLI-failure signatures,
  normalises them (IDs/paths/numbers → placeholders) and dedupes with counts.
- Raw deduped output: [`raw-mined.txt`](raw-mined.txt). Counts below are occurrences
  across all agents, so a high count means *repeatedly* tripped over.

Each finding is tagged:
**[DEFECT]** uedcli is wrong · **[UX]** uedcli is right but misleads ·
**[INFRA]** environment/substrate · **[AGENT]** the agent's own mistake, recorded
because a tool that is easy to misuse invites the mistake.

---

## 1. [DEFECT] `level materialize` post-verify rejects good builds over engine-stamped `Base`

**The single most costly defect of the run.** Deterministic, not flaky.

```
post-verify mismatch: on-disk /work/<id>.dx does not match the intended level —
actor 'BarrelFire_<rnd>' differs on property Base:
    built:    Base=LevelInfo'MyLevel.LevelInfo0'
    intended: Base omitted (class default none)
```

The engine stamps `Base` onto an actor resting in the level. The trunk never authored a
`Base`, so the typed effective-value compare sees a difference and **discards a perfectly
good map**. Occurred with several actor names (`BarrelFire`, `Barrel1`, …) across agents.

`Base` is an engine-injected runtime field of exactly the kind `direction/materialize.md` already
describes as "build output, not authored state" (alongside `Region`, `BasePos`/`BaseRot`,
`bSelected`, mover `Saved*`) — but it is **missing from `normalize.COMPUTED_PROPS`**.

**Cost:** every affected build fails and is thrown away. Each attempt is ~2.5 min, so a
retry loop burns 10+ minutes achieving nothing. The only escape is `--no-verify`, which
disables the safety check wholesale.

**Fix:** add `Base` to `COMPUTED_PROPS` (with the usual evidence + a regression test per
the "pin the finding" rule). Check its siblings too — anything the engine assigns on
`PostBeginPlay`/attachment.

---

## 1b. [DEFECT — SEVEREST] `--no-verify` can write a PARTIAL map and report SUCCESS

Found by the `DiveBar` agent while root-causing a "fullbright room", and it is the worst
defect of the run because **it produces a broken artifact while printing success**.

Reproduced directly: one `level materialize --no-verify` run of an **unchanged** trunk
produced a **23,126-byte** map while printing a clean `materialized <path>` and exiting 0.
A later `--no-verify` run of the *same* trunk produced the correct **191,332 bytes**.
The ~15 KB difference is the **baked lightmap**: the runt had geometry but no light bake,
so every BSP surface rendered at full texture brightness — visually identical to
"ambient light added everywhere", which is what sent the investigation down a
`ZoneInfo` blind alley for a long time. (`Engine.ZoneInfo`'s default `AmbientBrightness`
is **0**, confirmed offline — the ZoneInfos were innocent.)

**Why this is worse than it looks:** `--no-verify` is documented as skipping the
*post-build check*. In practice it also permits shipping a build that never finished.
Combined with §1, the two defects form a trap:

> the `Base` false-positive makes verify fail on a good build → the user is pushed to
> `--no-verify` → `--no-verify` can silently emit a runt → the user ships a broken map
> believing it succeeded.

**Fixes needed, in order:** (a) `--no-verify` must still assert the build *completed*
(non-runt size / lightmap present / structural self-check) — skipping the *comparison* is
not the same as accepting *anything*; (b) fix §1 so the flag is not needed in the first
place.

**Cost paid:** a milestone-4 build shipped unlit and was mistaken for a lighting-design
failure; hours of the wrong investigation. The orchestrator also used `--no-verify` for a
user-facing delivery on this advice (that map was later verified in-game to be a
complete, lit build — but only by luck, not by any check the tool performed).

**INDEPENDENTLY REPRODUCED** by the `ContainerYard` agent, on a different level, with a
worse ratio: `--no-verify` **printed success and wrote a 14 KB stub** where a good build
of that level is **~350 KB**. Every subsequent `--game` preview then hung 10+ minutes
rendering an empty map, which *looked exactly like container contention* and sent the
agent chasing the wrong cause. **Cost: ~70 minutes.**

Two independent reproductions on two different levels make this the most confirmed defect
in this document. Note the second agent's added observation: **`level preview --game` has
no `--no-verify` escape of its own**, so once post-verify false-positives block you (§1),
`--no-verify` + `preview --map <file>` is the *only* route — which forces every user
straight into the runt trap.

---

## 1c. [DEFECT] Auto-stubbing is implemented but NEVER CALLED — and v68 props "place" silently

Two defects compounding, found by the `DiveBar` agent.

**(a) The actor placed successfully and did not exist.** The agent placed ~15 `Endemia.*`
decorations. Every command reported success. None of them were in the built map. It got
no signal at all until, having placed more, `level materialize` refused the whole level:

```
materialize failed (nothing written): level references v68 code package(s) with no v69
stub: Endemia — the v69 editor cannot load a v68 `.u` directly; build the stub(s) first
(`uedcli substrate stub <pkg>`) or the referencing level cannot materialize
```

The refusal message is **good** — it names the package and the fix. The defect is that it
arrives at *build* time, an unbounded distance from the `actor add` that caused it, and
that placing an actor of an unloadable class is accepted silently in the first place.
**A class whose package cannot be loaded should fail at `actor add`, naming the package.**

**(b) The automatic stub build has no callers.** `stub.py:322` defines
`stub_missing_packages`, documented in its own docstring as *"the lazy auto-trigger
core"* — for each missing package with a v68 `.u` on the composed search path, build or
reuse its v69 stub. It is fully implemented and **nothing in the codebase calls it**
(grep across `uedcli/`: the only other occurrence is a reference inside a neighbouring
docstring). Stubbing is therefore manual-only via `uedcli substrate stub <pkg>`, and the
user's stub cache (`~/.uedcli/cache/stubs/`) was **empty**.

Everything else needed for it to work was in place:

- `Endemia.u` exists at `<...>/DX/LUM/System/Endemia.u`
- that dir is the FIRST entry on the project's composed search path
- `_is_stub_candidate` (predicate: "a v68 `.u` exists on the search path") would have
  returned true

So the designed behaviour would have handled this exactly, had anything invoked it.

**Fix:** (i) validate class/package loadability at `actor add`; (ii) call
`stub_missing_packages` from the materialize pre-pass — the code already exists.

**(c) …and the manual stub CANNOT be built either — `Endemia` is currently un-stubbable.**
Attempted at Andrzej's instruction, 2026-07-26:

```
$ uedcli substrate stub Endemia
Failed loading package: Can't find Function in file 'Function DeusEx.DeusExDecoration.BeginPlay'
Exiting due to error                                    # exit 2, cache unchanged
```

Stubbing the dependency first fails the same way:
`uedcli substrate stub DeusEx` → `Exiting due to error`, exit 2, cache still empty.

**Why this is structural, not a one-off.** Stubbing is *mesh-preserving* — it keeps assets
and strips code. `Endemia` is a **mod code package whose bytecode links against game code
functions** (`DeusEx.DeusExDecoration.BeginPlay`). Loading it against a code-stripped v69
`DeusEx` cannot resolve that reference, so the stub build dies. `stub_closure` resolves
only **one hop** and raises on anything deeper, so the "stub the dependency first" route is
not available either.

So `Endemia.*` props are **unusable in this pipeline today**, and the `DiveBar` agent's
switch to `DeusEx.*` equivalents was the correct call, not a workaround to be undone.

Exit-code behaviour is CORRECT here (exit 2 on failure) — worth recording because so many
neighbouring failures in this document are silent successes. The weakness is only the
message: the actionable line (`Can't find Function …`) is separated from the terminal
`Exiting due to error` by blank lines and an out-of-order `stubbing Endemia…` progress
line, so the cause is easy to miss.

---

## 1d. [DEFECT] `class list`'s two views DISAGREE about whether a package exists

Found by the `DiveBar` agent while tracing §1c:

- `class list --subclass-of <X>` **offers `Endemia.*` classes**, unmarked and
  indistinguishable from usable ones.
- unfiltered `class list --flat` reports the substrate packages as only
  `DeusEx, DXOgg, Engine, TNM` — i.e. **`Endemia` does not exist**.

Both are the same noun in the same project. A discovery verb that advertises a class the
build cannot load — with no marker saying so — is how the ~15 phantom props got placed in
the first place. **Discovery should not offer what materialize will refuse**, or should
mark it plainly.

Related: the agent also reported that **nothing anywhere tells you a built map is missing
its light bake** — not `level status`, not `level doctor` (trunk-only, static), not
materialize's own output. `ls -la` on the `.dx` was the only tell. Surfacing
"lighting baked: yes/no" (or a size delta vs the previous build) as a materialize output
line would have collapsed the entire §1b investigation into one glance.

---

## 1e. [DEFECT] `level doctor` says "no issues found" while brushes physically block doorways

Found by the `TubePlatform` agent, and **the single most expensive problem of its session**.

`level doctor` reported `no issues found` for the entire session while **four additive
brushes blocked three doorways**:

- a cable tray ran across *every* wall opening in the level at 36 uu above the floor —
  above DX's `MaxStepHeight` (25), so it **barred** the plant door, the vent-route niche
  and the exit passage;
- an ad panel cut the plant doorway from 128 uu to **56 uu** (crouch-only);
- another ad panel covered the niche mouth entirely;
- two crates stood in front of the vent.

`docs/usage.md` advertises doctor as catching "invisible walls". This is exactly that
class of fault, it is **statically checkable offline** against the trunk, and doctor
passed the level clean throughout. The agent found all four only by reading `--game`
renders and then hand-deriving the arc geometry in polar coordinates in Python.

**Why it matters:** a level that *builds* and *renders* can still be unplayable, and the
one verb whose job is to catch that reported success. A silent false-negative in a
checking tool is worse than no tool, because it is trusted.

---

## 2. [DEFECT] Editor containers leak, and there is no warm-editor reuse

`apply.py` mints a fresh container per invocation:

```python
ed_id = uuid7()                       # a NEW container name every single call
...
finally:
    stop_editor(ed_id, state_dir)     # only cleans up on a normal unwind
```

Because teardown lives only in `finally`, any run that is **killed or wedges** strands its
container. Observed: **9 stale `uned-*` containers accumulated in about an hour**, two of
them still running an hour after their command had gone, one already OOM-killed
(exit 137). On a 4-core/7.7 GB box this exhausted RAM and swap and caused cascading
failures across all three agents.

There is **no warm-editor path in the code at all** — grep finds warm-container logic only
in `preview_game.py` (the game-preview container, which *is* correctly reused: exactly one
`uedcli-game-preview-1000` existed throughout). `direction/materialize.md` describes a
"warm per-user editor container for materialize"; that is the *target*, not the
implementation, and the gap is invisible from the docs.

**Fix candidates:** (a) reap orphans on startup by label/age; (b) implement the warm
editor container the direction doc already specifies; (c) at minimum, make the editor id
pinnable so a caller can opt into reuse.

---

## 3. [DEFECT] Fixed timeouts are far too tight under load

| Bound | Observed |
| ----- | --- |
| `OBJ DEPENDENCIES PACKAGE=MyLevel did not complete within 20 attempts (20s)` | **19 occurrences** — by far the most common failure |
| `MAP SAVE never produced a finished file ... (after 600s, bound 600s)` | wedged, then burned the full **10 minutes** before giving up |

On an idle machine the same build completes in **~50 seconds**. So these are not slow
builds — they are a fixed 20 s bound colliding with a loaded box. The 600 s save bound is
the opposite failure: when the editor really has wedged, the caller waits ten minutes to
find out.

**Fix candidates:** scale the bound to observed progress rather than wall-clock; detect a
wedged editor actively (is the process doing work?) instead of waiting out a fixed timer;
make bounds configurable.

---

## 4. [DEFECT] `actor preview` with no name source silently does nothing

```
$ bin/uedcli actor preview --annotate name --size 900 --out shots/x.png
$ echo $?
0                      # exit 0, no output, NO FILE WRITTEN
```

It needs `actor find | actor preview -` or explicit names. With neither it selects the
empty set, writes nothing, prints nothing, and **exits 0**.

This violates the project's own "**No silent half-answers**" rule. It cost real time: the
orchestrator hit it, assumed the render had succeeded, and only noticed the missing file
later. Empty *stdin* being a clean no-op is deliberate and fine; **omitting the argument
entirely is a different case** and should be an error naming what is missing.

---

## 5. [UX] Verb/flag guesses that a careful reader still gets wrong

Each of these is uedcli behaving as designed, but repeatedly mis-guessed:

| Guessed | Reality | Note |
| ------- | ------- | --- |
| `actor find --class X` | `--exact-class` / `--subclass-of` | Both an agent **and the orchestrator** reached for `--class` first. Two independent readers guessing the same wrong flag is a naming signal. |
| `texture show` | `texture` has only `sync,list,search,tags,classify` | `direction/asset-catalog.md` describes `show`/`preview` for the asset catalog; the noun doesn't have them yet. Docs describe the target, users type the target. |
| `actor add --folder …` | `--folder` lives on the **generators** | `uedcli: error: unrecognized arguments: --folder light.plant`. A deliberate decision (2026-07-24) that users keep tripping on. |
| `texture search --color teal` / `cyan` | 12-word vocabulary: black white grey red orange yellow green blue purple pink brown tan | Hit while building a **cyan neon** level — the one colour it needed. The error does list valid values (good). |

**The `--color` vocabulary deserves attention.** It is a closed 12-word list with no
synonyms; "teal" and "cyan" both fail. For a tool whose users describe colour in natural
language, accepting synonyms (or nearest-match with a note) would remove a whole class of
dead end.

---

## 6. [UX] Human summaries on stderr are correct, and still cause a piping trap

```
surface selector must be BRUSH:SELECTOR, got '6 face(s) matched'
```

`brush poly find` does the right thing — selectors to **stdout**, `6 face(s) matched` to
**stderr** (verified). The agent captured `2>&1` and piped the merged stream, so the
human summary was fed to `brush poly set` as a selector.

Not a defect. But the failure is *silent until the next verb chokes*, and the error names
the symptom rather than the cause. A consuming verb that receives something
unparseable could say so: "this looks like a human summary — did you pipe `2>&1`?"

---

## 6b. [DEFECT?] Textured signage renders MIRRORED — seen in two independent levels

Observed in-game, by two agents who never communicated, on two different levels:

- `ContainerYard` `m3-1-gate.png` — the gate sign reads `ONICA` **reversed**.
- `TubePlatform` `m4-keypad.png` — platform advertising panels render their text **reversed**
  (visible as mirrored lettering across several panels).

Both used ordinary surface texturing on wall faces. Two independent agents producing the
same artefact points at a **tool-side cause** rather than two coincidental authoring
mistakes — most likely a U-axis sign convention in surface alignment (`brush poly align
--wall`, or the default alignment on a subtracted face whose winding faces the viewer).

**Why it matters disproportionately:** a mirrored *texture* is invisible on most surfaces —
brick, metal, concrete are all near-symmetric — so this defect stays silent until someone
applies a texture containing **text**, which is exactly what signage, adverts, posters,
and DX's readable world-detail are. It is also invisible in `actor preview` wireframes and
in `--native` draft renders; only the lit in-game render exposes it.

**FINAL ROOT CAUSE — a single line in uedcli's own source.** The `TubePlatform` polish
agent read the code rather than guessing:

> **`builders._tex_basis()` computes `V = N × U`, so EVERY face emitted by EVERY uedcli
> generator has `U × V = +N` — the handedness the engine renders MIRRORED.**

That is systematic, not per-brush, and it explains why two agents who never communicated
produced identical mirrored signage on different levels with different verbs. It also
explains why `brush poly align --wall --fresh-frame` cannot fix it: **that verb calls the
same function**, so it re-synthesises the identical wrong-handed frame — byte-identical
output, as an earlier agent measured empirically without knowing why.

**There is no clean fix at the CLI today.** The only working lever found was
`brush scale --by -1,1,1` + `brush apply-transform` (the bake transforms texture axes by
the inverse-transpose and reverses winding when `det < 0`), plus a compensating
`actor rotate` — and on a `revolve`-baked brush even that is subtle: `--by -1,1,1`
*reflects* U about local X rather than negating it, so it took three passes to land.
Geometry was confirmed unchanged to <0.01 uu via `actor bbox` before/after.

**The real fix is in `_tex_basis`**, and it is one line. Everything below was a symptom.

---

Earlier partial findings, kept because each is independently true and separately fixable
(from the `ContainerYard` pass):

1. **Mirroring IS fixable by rotation, and the rule was simply undocumented.** A
   `--plane xz` sheet reads correctly from the **+Y** side; a sign meant to be read from
   **−Y** needs `--rotate 0,32768,0`. Nothing said so, so both agents placed signs facing
   the wrong way and got reversed text. *(This supersedes the earlier claim in this file
   that `brush build sheet` offers no way to un-mirror — it does, via facing.)*
2. **EVERY sheet is half-shifted.** `brush build sheet` puts the texture Origin at the
   sheet's **centre**, not its corner, so a sign texture is displaced by half its size
   unless corrected with `brush poly pan --to <w/2>,<h/2>`. This affects every sheet in every level,
   silently.
3. **Some sheets get a 90°-rotated texture frame** (`TextureU` running vertically), so the
   texture tiles on its side — two signs in one level.
4. **`brush poly align --wall --fresh-frame` does NOT fix any of this.** On a +Y face it
   re-synthesises the same vertical-U frame, byte-identical output. Rebuilding the sheet
   was the only route the agent found.
5. Separately, a **256×256 texture on a 128×128 sheet** shows only one quadrant — mostly
   transparent for masked signage. Sheet size must match texture size.

**Why it stayed invisible:** all of this is undetectable on brick/metal/concrete (near
symmetric, and a half-shift on a tiling texture looks identical). It only becomes visible
when the texture carries **text** — signage, adverts, posters — which is exactly the
readable world-detail Deus Ex depends on. It shows in neither `actor preview` wireframes
nor `--native` drafts; only a lit in-game render exposes it.

**Fixes:** document the facing rule; make the sheet texture Origin default to a corner (or
warn); have `poly align --fresh-frame` actually re-derive the frame for the face's real
orientation.

Reproduction material is in both levels' trunks under `_scratch/levelbuild/`.

---

## 7. [UX] Errors that are good, and worth keeping

Recording these so they are not "fixed" into something worse — they worked:

- `texture not found: CoreTexMetal.NYC_GrayMetal_A — no Texture of that name on the package path (author-time validation)` — catches a bad ref at author time instead of at build.
- `uedcli brush build cube: error: argument --at: coordinate must be X,Y,Z (3 comma-separated numbers), got '0,'` — names the offending value exactly as the conventions require.
- `brush build staircase: --depth must be greater than 0, got -8.0`.
- Unknown-colour error listing the whole valid vocabulary.

---

## 8. [DEFECT/UX] Obscure errors needing context

- `materialize failed (nothing written): level references v68 code package(s) with no v69 stub: Endemia — the v69 editor cannot load a v68 .u directly` — accurate but leaves the user with no next action. It should say how to build the stub.
- `1 'A package file must be specified.'` — leaked from the editor with no indication of which command or which package.
- `cannot read schema for DeusEx.Flare: package 'Engine' (needed for Engine.Actor) not found on the [path]` — correct, but a class-schema failure mid-build is opaque to a level author.
- `stash not found: 'probe'` — fine.

---

## 9. [INFRA] Not uedcli's fault, but shaping the experience

- **Host saturation.** 4 cores, 7.7 GB RAM. Three agents plus the orchestrator drove load to **~16** with swap fully exhausted; one container OOM-killed. Most "flaky editor" behaviour traced back to this.
- `CreateWindowEx failed: Success.` (4x) — Wine/X noise from the GUI editor.
- `docker exec ... wmctrl -l` returning non-zero (3x) — driving a GUI editor by window-manager queries is fragile.
- `docker exec ... sed -i ...` returned exit 4 while writing the Paths ini — a container killed mid-startup.

These are the motivation for the parallel **`headless-materialize`** spike: nearly all of
this disappears if materialize does not need a Wine-hosted GUI editor.

---

## 10. [AGENT] Mistakes the agents made themselves

Recorded honestly so the list above is not inflated:

- ~~No uedcli traceback ever reached an agent.~~ **CORRECTED.** That claim was made from
  the transcript mining alone and is **wrong**. The 2 `AttributeError`s the miner found
  (`'tuple' object has no attribute 'actors'`, `'list' object has no attribute 'get'`)
  were indeed the **spike agent's own harness script**, not uedcli — but the
  `TubePlatform` agent later reported uedcli leaking a **`BrokenPipeError` traceback**
  from `--folder` on `actor add`. So the "never let a Python exception reach the CLI user"
  rule **was** violated, in at least one path; the mining simply missed it (a signature
  the regex did not catch, or output the agent paraphrased rather than pasted).
  *Method note: absence of evidence in the mined signatures is not evidence of absence —
  the miner is a floor on what happened, never a ceiling.*
- `ModuleNotFoundError: No module named 'uedcli'` / `'PIL'` — ran system `python3` instead
  of going through `bin/uedcli` / the venv.
- Several agents idled waiting on background jobs whose completion never woke them,
  instead of running previews in the foreground.
- Agents repeatedly re-derived the same environment facts (texture sync cost, the
  `--color` vocabulary, the `Base` verify gap) because nothing surfaced them.

---

## 11. Cost items that are not errors

- **`texture sync` takes 30+ minutes** for 4,791 refs across 57 packages, with no progress
  output and no obvious resumability. Pre-seeding the catalog by copying
  `texture-catalog/` between projects works and is instant — but a first-time user has no
  way to know that, and would pay 30 minutes per project. The per-user decode cache
  underneath did **not** make a second project's sync fast.
- **Everything is `unclassified`**, so `texture search --tag` and description matching
  return nothing. Discovery is by name grep, package, or colour only. Correct per the
  "tool does not infer" decision, but it means the catalog's headline feature is inert
  until someone classifies — and no agent had a reason to.

---

## Ranked shortlist

1. **`Base` in `COMPUTED_PROPS`** (§1) — one-line class of fix, removes a defect that
   silently discards correct builds.
2. **Container leak + warm editor** (§2) — the root cause of the cascade.
3. **Timeout policy** (§3) — 19 failures from one over-tight bound.
4. **`actor preview` silent no-op** (§4) — violates a stated rule; cheap to fix.
5. **Naming/discoverability** (§5) — `--class`, `texture show`, `--folder`, colour synonyms.
6. **`texture sync` cost + progress** (§11).
