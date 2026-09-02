# Polish pass — shared brief

Andrzej played the three built levels and reported concrete faults. Your job is to **fix
them in your assigned level**, verify each fix in-game, and report. This is polish on a
finished level: **do not redesign, do not rebuild, do not add new areas.**

His overall verdict was *"really good job, but these need more polish"* — so the bar is
"stop it looking broken", not "make it different".

---

## 0. Read first — you inherit nobody's reading

1. `/home/neob91/Documents/Dev/uedcli/CLAUDE.md`
2. `/home/neob91/Documents/Dev/uedcli/_scratch/levelbuild/BRIEF.md` — the original build brief (render protocol, constraints).
3. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/deusex/human-scale.md` — **load-bearing for fault 1.**
4. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/general/textures-and-surfaces.md` — for fault 2.
5. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/deusex/recipes/datacube.md` — for fault 3.
6. `/home/neob91/Documents/Dev/uedcli/docs/leveldesign/general/movers.md` + `.../general/recipes/mover-door.md` — for fault 4.
7. `/home/neob91/Documents/Dev/uedcli/docs/usage.md` as needed. **Never guess a flag.**

**Orient before editing:** `bin/uedctl level status`, `actor find`, and `Read` several of
your level's existing shots so you know what it looks like now.

---

## 1. Decorations are sunken into the floor  ← affects every level

**The rule:** an actor's `Location` is its **CENTRE**, and `CollisionHeight` is its
**HALF-height** (the DX player is 95 uu tall with `CollisionHeight` 47.5). So a decoration
placed with `Z = floor` sinks by exactly half its height.

**Correct placement is `Z = floorZ + CollisionHeight`.**

Do this properly, per class — do not apply one blanket offset:

```bash
bin/uedctl actor prop get <ActorName> CollisionHeight     # resolves the class default
```

Walk every placed decoration (`DeusEx.*` props: bottles, crates, chairs, barrels, bins,
lamps, cans…), get its `CollisionHeight`, work out the floor Z beneath it, and set
`Location` Z to `floor + CollisionHeight`. Where a prop sits on a table/shelf/crate, the
"floor" is that surface's top, not the room floor.

Verify in-game: props should **rest on** surfaces, not sink into them or hover.

## 2. Textures — wrong choice or misaligned

Look at your level's in-game shots and find surfaces where the texture reads wrong:
stretched, mis-scaled, obviously tiling at the wrong size, rotated, or simply a poor
material for the surface. Fix with `brush poly find` → `brush poly set` / `brush poly
align` (`--wall` / `--floor` / `--ring`).

**Known tool limitation, do not fight it for hours:** `brush build sheet` provides no way
to *un-mirror* a texture, so a sheet can render its texture reversed — visible when the
texture contains text (a sign reading backwards). If you hit that, either re-place the
sheet with the opposite facing, use a non-text texture, or log it and move on.

## 3. Datacubes have no text

Set both properties, per the recipe:

```bash
bin/uedctl actor prop set <DataCube> textTag=<TextName> TextPackage=<PackageName>
```

**Important:** the *text itself* is compiled into a `.u` package by `ucc make`
(`#exec DEUSEXTEXT IMPORT`), which is an asset-pipeline step **outside uedctl**. So you can
and must wire up `textTag`/`TextPackage` correctly and write the `.txt` source, but you
may not be able to produce the final package yourself.

**Do not fake it and do not claim it works if you have not seen text in-game.** Write the
`.txt` files, set the properties, and report precisely what package build is still needed.

## 4. Movers vanish completely into walls

A sliding door / grate / shutter that retracts **entirely** out of sight looks magical and
broken. Real ones leave part of the leaf visible in its pocket.

For every mover in your level: compare its keyframe offset against the brush's own size
along the direction of travel, and make sure the **open** pose leaves a visible portion
(a reasonable rule of thumb: keep at least ~15–25% of the leaf showing, or stop it short
of full retraction). Use `mover key` to adjust; do not rebuild the mover.

Check the **closed** pose too — the leaf must fully cover its opening when shut.

## 5. Floating / misaligned geometry

Find brushes and actors that hang in the air, intersect wrongly, or sit off-grid. Fix by
snapping to the power-of-two grid and reseating them on their supporting surface.

---

## How to verify — BOTH renderers

- Fast geometry checks: `bin/uedctl level photo --native` (~1s, no lighting).
- **Truth: `bin/uedctl level photo --game`** — batch ALL of a check's shots into ONE
  invocation; the container is shared and serialised.
- Wireframe: `bin/uedctl actor find | bin/uedctl actor diagram - --annotate name --size 900 --out <proj>/shots/<name>.png`
- **`Read` every picture you produce.** Judge the fix by looking at it.

## Traps that already cost this project hours

- **`level materialize --no-verify` can write a RUNT and report success.** Two agents hit
  it. After any build, **check the file size** against a known-good build of that level —
  a fraction-size `.dx` means the build silently failed. Never trust `exit 0` + a success
  line alone.
- Post-verify raises **false positives** (`actor ... MISSING from the built map`,
  `differs on property Base`) on builds that are actually fine — `--no-verify` is the
  workaround, but see above.
- `level photo --game` has **no `--no-verify`**; use `--map <file>` against a map you
  built and size-checked.
- **Check exit codes.** `cmd | tail` reports *tail's* status — use `${PIPESTATUS[0]}` or
  `set -o pipefail`. And a zero exit does not prove success: verify the artifact.
- The editor wedges under load (`OBJ DEPENDENCIES ... within 20 attempts`). Sleep ~30s and
  retry, up to ~5 times. Run previews in the FOREGROUND; do not idle waiting on jobs.

## Constraints

- Work only inside your own level's project dir under `_scratch/levelbuild/`.
- **No `git` operations at all.** No commits, no staging, no branch changes.
- **Do not modify uedctl's source, tests, or docs** — except appending findings to
  `dev/docs/spikes/levelbuild-friction/agent-reports.md` (append only; other agents share it).
- Do not spawn subagents. Do not kill containers you did not create.

## Report

Per fault: what you found, what you changed, and the shot that proves it. Say plainly what
you could NOT fix and why.
