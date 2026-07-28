+++
priority = "p1"
kind = "owner-question"
summary = "Two sessions were dispatched at one worktree and nearly clobbered each other; the build is done, the process question is not."
depends-on = ["native-texture-decode"]
+++

# Two sessions were assigned `native-texture-decode` in the same worktree

**RESOLVED — the collision is over and the work is DONE.** *(Updated 2026-07-28.)* The build was
finished by a single session and the item is at `dev/docs/board/done/native-texture-decode/`; every
finding listed under "What it had established" below was independently re-derived and is now fixed
and pinned by a test. **What survives here is the PROCESS question**, which nothing about the build
answers: two sessions were dispatched onto the same item in the same worktree, and only luck — the
second one running `git status` before its next write — kept one from silently dropping the other's
work. Kept in `inbox/` for that reason.

*(Original status, for the record: **STRUCTURAL — the work is PARKED, not done**, 2026-07-27.)*

## What happened

Two agent sessions were dispatched to take board item `native-texture-decode` from "plan has
unresolved review findings" through plan-review round 2, the eight-slice build, and the build gate —
**both in the worktree `.claude/worktrees/native-texture-decode` on branch `native-texture-decode`**,
and both told the worktree was clean with zero commits of its own.

The second session discovered the first only after making four edits to `plan.md`: `git status` showed
ten modified files, a **staged** `git mv` of
`inbox/three-design-calls-the-native-texture-formats/spec.md` →
`to-build/native-texture-decode/spec.md`, a staged deletion of that inbox item's `overview.md`, and a
new `to-build/native-texture-decode/questions/` directory — none of it the second session's, all of it
written in the preceding four minutes, and all of it resolving the **same** review-finding list.

## Why it stops the work rather than being coordinated around

- **Every write races.** Both sessions read-modify-write whole files. `plan.md` briefly held hunks from
  both, and either session's next write would have silently dropped the other's.
- **Neither can commit.** `CLAUDE.md` "Commits" forbids committing another session's hunks and requires
  a clean index before staging; the index was already carrying the first session's `git mv`.
- **Duplicated build.** Two divergent implementations of the same eight slices cannot both
  squash-merge, and the merge target is one branch.

## What the parked session did

Reverse-applied its own four `plan.md` hunks (`git apply -R`, checked clean first) so `plan.md` holds
**exactly** the first session's state, and left everything else of the first session's untouched. Its
own work is preserved as a patch at `_scratch/ntd/plan-MINE.patch` (gitignored) — it is not lost, and
it is not in anybody's way.

## What it had established, which the other session may or may not have

Verified independently. **All five landed** — recorded here as the reason the parked session's work
was not wasted, not as outstanding items:

- The `bMasked` read rule (owner ruling 2026-07-27: tag if present, else the resolved class default)
  written into S2b with its evidence chain — `unrealed/t3d.md`'s ✅ member-precise default-diffing, the
  `DeusEx.Rat` `RotationRate=(Pitch=4096)` measurement, `propedit`'s `STRUCT_FILL = "default"`,
  `normalize.compare_view` — and the scope it pulls in, `uprops.resolve_class_defaults`.
- **Re-measured 2026-07-27:** `uned/UED22/` holds **317** `bMasked` exports, all `True`, over 34
  packages / 1,998 `Texture` exports (84 `DeusExDeco.u`, 44 `DeusExItems.u`, 35 `DeusExUI.u`, 32
  `DeusExCharacters.u`, 29 `Engine.u`, 23 `uwindow.u`, 6 `Extension.u`, 4 `DeusEx.u`, 2 `ubrowser.u`),
  so S2b's "no committed fixture carries the flag, it would ship untested" premise is **false**.
- `uedcli/tests/test_engine_facts.py`'s `test_utexture_bmasked_is_stored_presence_only_and_never_as_false`
  iterates only the two committed fixtures, which hold **zero** masked textures, so its
  `assert v is None or v[1] is True` **passes vacuously today**. Its docstring also states the
  presence-only reading the ruling replaces.
- **Pre-slice test baseline, measured on this worktree 2026-07-27:** `bin/test` → **9092 passed, 76
  skipped, 64 deselected, 0 failed**, exit 0, in 174 s. `cargo` is **not installed** on this machine, so
  `bin/test` skips the Rust goldens — a green run here exercises less than it looks.
- The `array: "mips" | "comp-mips"` provenance field belongs in **S2**, not S4: S1 already implements
  the selection rule, so the answer exists two slices before BC1 does, and S2b can assert on it.

## The decision needed — still open, and it is not about this item

Ownership resolved itself: one session finished the work. **The process question did not.** Nothing
prevents this happening again — a worktree carries no record of who is working it, and both sessions
were told it was clean with zero commits of its own. The near-miss cost nothing only because the
second session happened to run `git status` before its next whole-file write.

Worth ruling on: whether a dispatched session should claim a worktree somehow before writing, or
whether the answer is simply never to dispatch two sessions at one board item.
