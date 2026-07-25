# `OBJ DEPENDENCIES` untextured-poly correlation (D-Q2) — 2026-06-20

**Status: RESOLVED, live-confirmed.** An unset poly (`Texture=` absent) contributes **zero**
lines to an `OBJ DEPENDENCIES` brush block. D-Q2 ("only already-textured polys consume a line")
is **CONFIRMED** — `qualify.qualify_level_textures`'s `polys = [p for p in ... if p.texture is
not None]` filter is correct as written; no code change needed.

A second, independent finding fell out of the same session and is now also **RESOLVED, FIXED,
and live-confirmed reliable (5/5)**: the original settle-and-read recipe was unreliable for two
compounding reasons — see "Why the read looked non-deterministic, and the fix" below.
`qualify.dump_obj_dependencies` now retries with a guaranteed-flushing filler + a real
completion-marker check, rather than one fixed sleep.

## Headline

| Question | Verdict |
|---|---|
| Does an unset poly (`Texture=` line absent) consume an `OBJ DEPENDENCIES` line? | **NO** — confirmed live, exact bytes captured below |
| D-Q2 ("only already-textured polys consume a line") | **CONFIRMED** |
| Is the group required to bind, even when the texture has one? | **NO** (same session, see `unrealed/quirks.md`) |
| Does a qualified `Texture=` auto-demand-load its package? | **NO** (same session — see `unrealed/quirks.md`; fixed in `apply._ensure_load`) |
| Does the walk's object enumeration order/completeness vary across identical calls? | **NO, apparent only** — `Editor.log` is a 4KB stdio-buffered stream; an under-powered settle command left genuinely-complete output unflushed/invisible. Fixed: retry with a guaranteed-verbose filler + completion-marker check |
| Is there a separate, real blocking issue too? | **YES** — a "Cleaning up..." GC-progress dialog (titled `xmessage`) appears during GC passes and never auto-closes headless; must be dismissed each retry |

## Setup

Reused `_scratch/texread/rt/` (the runtime dir from
`2026-06-19-read-surface-texture-package.md`, install content already wired). Probe brush
built via `builders.cube(128,128,128)` + `make_brush_actor` (NOT hand-typed T3D — a hand-typed
attempt crashed the editor on import; the builder path is validated and round-trips cleanly),
with `polys[0].texture` set to a real qualified ref, `polys[1].texture = None` (genuinely unset
— no `Texture=` line emitted at all), `polys[2].texture` set to `Engine.DefaultTexture`
explicitly, and `polys[3..5]` left at the builder default (`None`):

```python
brush = builders.cube(128, 128, 128)
brush.polys[0].texture = "CoreTexMetal.Area51Wall_A"   # 2-part, no group (see quirks.md)
brush.polys[1].texture = None                           # genuinely unset
brush.polys[2].texture = "Engine.DefaultTexture"
actor = make_brush_actor("ProbeBrush", brush, csg="add")
```

So the brush has **2 textured polys** (0 and 2) and **4 unset polys** (1, 3, 4, 5).

Driven via `wine_ctl.py exec` against an ephemeral `uned-objdep-corr` container (own WINEPREFIX
volume), never the persistent `dx-lum-uned`:
1. `OBJ LOAD FILE=CoreTexMetal.utx PACKAGE=CoreTexMetal` (required — see quirks.md; the package
   isn't auto-demand-loaded on import even though it's on `Paths`).
2. `MAP GRID X=1 Y=1 Z=1` → `MAP IMPORTADD` the probe T3D.
3. Confirmed the binding actually worked first, via `MAP EXPORT` re-export
   (`grep Texture=` showed `Texture=Area51Wall_A Link=0` and `Texture=DefaultTexture Link=2`
   only — bare names, as expected, the unset polys carrying no `Texture=` at all).
4. `OBJ DEPENDENCIES PACKAGE=MyLevel`, then settled (a trailing noisy `OBJ LIST` command +
   sleep, per the 2026-06-19 spike's recipe) and read the log forward from a pre-query
   `stat -c %s` offset.

## The confirming capture

One dependency walk (auto-triggered around a `MAP NEW`, same underlying engine code path as
the explicit console verb) captured our brush's **entire** `Engine.Polys` block, byte-for-byte
(`_scratch/objdep_corr/dump_clean.txt` lines 2–4):

```
Log:       Class Engine.Polys
Log:       Texture CoreTexMetal.Metal.Area51Wall_A
Log:       Texture Engine.DefaultTexture
```

**Exactly 2 `Texture` lines for a 6-poly brush with exactly 2 textured polys.** The 4 unset
polys (1, 3, 4, 5) contributed nothing — no placeholder, no `Texture Engine.DefaultTexture`
implicit fallback, nothing. This directly answers D-Q2: a null `Texture` pointer is not a graph
reference, so the dependency walker (which only prints **referenced** objects) skips it
entirely, exactly as `qualify_level_textures`'s docstring already assumed.

(Note the qualified ref re-appeared here as the **3-part** `CoreTexMetal.Metal.Area51Wall_A`
form — the engine's own internal name includes the group even though our T3D referenced it
2-part. This is exactly why `qualify.qualify_level_textures` applies `_strip_group` to whatever
the dump reports, rather than assuming the dump will already be 2-part.)

## Why the read looked non-deterministic, and the fix

`OBJ DEPENDENCIES PACKAGE=MyLevel` does not walk only brushes — it enumerates **every** object
belonging to the package (`Level`, `Model`, `LevelInfo`, one `Camera` cluster per
viewport/browser, `Brush` actors, …), printing one full `Package MyLevel references:` record
per object. Repeated attempts on an unchanged level looked wildly inconsistent — different
attempts stalled or truncated at different points, sometimes with an `xmessage` dialog visible,
sometimes not. Two genuinely independent root causes, both confirmed live and both now fixed:

**1. `Editor.log` is a 4KB stdio-buffered stream.** Confirmed directly: every observed log-size
delta across this entire investigation was an **exact multiple of 4096 bytes** (9162→13258→
17354→21450, each step +4096). Content the editor has already written can sit invisible to an
external `stat`/`tail` reader until *something* pushes total bytes-written-since-the-last-flush
past the next 4096-byte boundary. The original recipe's settle command,
`OBJ LIST CLASS=Mesh NAME=zzz`, is a **silent no-op** whenever nothing matches that name (true
here — `zzz` matches no Mesh) — so it could add zero bytes and never force a flush, leaving a
genuinely-already-complete dump looking "stuck" purely because the read happened first. Direct
proof: re-running the exact same already-stalled state with one large filler instead
(`OBJ LIST CLASS=Class`, which lists every loaded class — ~28KB, always non-empty) flushed
*immediately*, and the previously-"missing" `Texture CoreTexMetal.Metal.Area51Wall_A` line for
our brush was sitting right there, already written, the whole time.

**2. A separate, real blocking dialog.** A "Cleaning up..." GC-progress dialog (window titled
literally `xmessage`, confirmed by screen-cropping a full-root screenshot at its `wmctrl -l -G`
geometry — `import -window <id>`/`xwd -id <id>` both captured the *editor's* toolbar instead,
an unexplained artifact, but cropping the **root** screenshot at the dialog's absolute
coordinates worked) appears around the GC pass (`Collecting garbage`/`Purging garbage`) that
fires on nearly every `MAP NEW`/`IMPORTADD`/`REBUILD`. It does **not** auto-close headless —
confirmed sitting unattended for 60+ seconds with zero progress — and blocks every subsequent
console command from reaching the Command box until dismissed. Dismiss via `xdotool
windowactivate --sync <id>` then a **window-less** `key Return` (NOT `xdotool key --window
<id>` — that throws `X Error: BadWindow`; wine ignores synthetic `--window` events, per
`commands.md`). This is unrelated to D-Q2/the buffering issue, but compounds it: while stuck,
*nothing* — including the flush-forcing filler — reaches the editor at all.

**The fix (`qualify.dump_obj_dependencies`, live-confirmed 5/5 rounds):** on each of up to 20
retry attempts, dismiss any stuck dialog (`Driver.dismiss_blocking_dialog`), drive the
guaranteed-verbose filler `OBJ LIST CLASS=Class` (forces a flush every time, unlike the old
silent-no-op filler), sleep briefly, then check the text read since the pre-query offset for
the walk's own completion marker (`"N Deleted Objects"`, which always follows a finished
`Dependencies of <pkg>:` walk). Five fresh-container rounds (`MAP NEW` → `OBJ LOAD` →
`IMPORTADD` → query) all completed within 1–2 attempts and correctly captured both of the
brush's texture lines every time. Raises `TimeoutError` rather than ever returning a
possibly-partial dump if 20 attempts aren't enough.

## Two more bugs the fix itself exposed (real `qualify_level_textures` correlation, not the spike)

Running the ACTUAL `qualify_live_level` against a real container (not canned test text) against
a single-brush level immediately surfaced 2 more real issues, both fixed:
1. **The dump isn't limited to our brushes.** The filler `OBJ LIST CLASS=Class` lists a class
   literally named `Engine.Polys`, polluting a naive full-text parse with a spurious 3rd block;
   and the level's own internal BSP `Model` legitimately contributes its own (always-empty)
   `Engine.Polys` block, independent of any authored brush. Fixed: `dump_obj_dependencies` now
   isolates the current walk to its own header→`Objects:` segment (`_segment_since_header`/
   `_blocks_only`), and `qualify_level_textures` drops EMPTY blocks symmetrically from both
   sides of the correlation (an empty block can never correspond to a brush we need to patch,
   whether it's the level's Model or a genuinely all-untextured authored brush).
2. **A stale earlier walk's own completion marker can satisfy the check** before the CURRENT
   walk's has even flushed (`Editor.log`'s 4KB buffering can surface old, already-terminated
   "Dependencies of MyLevel:.../Deleted Objects" text in the same read burst as a brand new,
   still-incomplete header). Fixed: the completion check is anchored to text after the LAST
   header, never the bare presence of the marker anywhere in the read.

## Full end-to-end verification (`export_and_qualify`, real fresh per-session editor)

With both fixes in place, `qualify.export_and_qualify` was run for real (not mocked) against a
freshly `ensure_editor`'d per-session container, end to end: offline export → fresh editor →
ensure-load the `.dx`'s own manifest → `MAP LOAD` → qualify → teardown. Took ~26s. Along the
way this surfaced FOUR more pre-existing bugs, none specific to this session's new code, all
now fixed (see `unrealed/quirks.md` "Containers / package resolution" for the full detail on
each): a stale cached `dx-lum-uned` Docker image with a pre-rename `ENTRYPOINT`; a wrong,
nonexistent `/opt/UED22/System/UnrealTournament.ini` ini path; a `sed` multi-line-append
syntax bug that only ever manifests with 2+ paths; and resolved package paths being
host-absolute when the container only has `/repo` bind-mounted. A final clean run against a
probe using only `Engine.DefaultTexture` (avoiding the separate, still-open transitive-package-
dependency gap — see `board/to-spec.md`) returned a correctly fully-qualified `Level`.

## Cross-links

- [`2026-06-19-read-surface-texture-package.md`](2026-06-19-read-surface-texture-package.md) — the `OBJ DEPENDENCIES` mechanism this spike refines.
- [`2026-06-18-deusex-content-install.md`](2026-06-18-deusex-content-install.md) — the runtime-dir/install-content recipe reused here.
- `unrealed/quirks.md` "T3D format" — the group-optional and demand-load findings from this same session.
- `plans/2026-06-20-uedctl-export-and-qualify-plan.md` (landed; plan deleted) — D-Q2, Task 1, Task 4.
