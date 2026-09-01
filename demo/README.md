# demo/ — the uedcli pitch demo, as code

A short pitch video built from scripts, not hand-recorded, so it's iterable and reproducible.
Story: a UnrealEngine 1.0 nightclub authored entirely as text — verbs compose, git is the source
of truth, the editor is only the compiler, and geometry is checked with exact measurements instead
of eyeballed screenshots.

## Pipeline

```
showcase-bar.sh ──builds──> $UEDCLI_LEVEL (NEON STRATA club)
                             │
                capture-club-shots.sh ──level photo --game──> out/mp4src/club/shot-*.png
                                                                │
mp4-beatsheet.md (beats + narration) ──mp4.py──────────────────┴──> out/pitch.mp4
```

```bash
cd demo
export UEDCLI_LEVEL=neon-strata UEDCLI_HOME=.uedcli-home
make club   # builds the level (./showcase-bar.sh)
make shots  # captures out/mp4src/club/shot-*.png from the built level (needs the game container)
make mp4    # → out/pitch.mp4 (needs ffmpeg)
make clean
```

## Editing

- **Level**: everything is in `showcase-bar.sh` — geometry, textures, lighting, all real `uedcli`
  commands. Placements that sit flush against another surface (a bottle on a shelf, a sign on a
  wall, a cushion on a seat) are verified with `brush measure relation` against their target
  surface, not eyeballed — see the `flush()` helper.
- **Narration/pacing/shots**: `mp4-beatsheet.md` — one row per beat, wired to `mp4.py`'s `BEATS`
  list. Change wording there, re-run `make mp4`.
- **Camera shots**: `capture-club-shots.sh` — one `level photo` pose per named shot. Re-run after
  any level change so the beat sheet's images stay current.

## Money shot

The hero shots are lit `level photo --game` frames of the finished club — real lighting, real
textures, no editor GUI ever opened. `capture-club-shots.sh` is what produces them; there is no
manual screenshot step.
