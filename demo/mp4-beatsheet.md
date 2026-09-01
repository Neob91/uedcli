# MegaGrant pitch MP4 — beat sheet (~1:35)

Target: a short pitch video for the Epic MegaGrants form. Show, don't tell. The finished club is
the "wow"; the text/git/measure beats are the "why fund this." Kept deliberately lean — every beat
either shows the level or substantiates a specific claim about the tool, nothing else.

| # | Time | Visual | On-screen / narration |
|---|------|--------|-----------------------|
| 1 | 0:00–0:10 | Cold open: best **club** shot | "An UnrealEngine 1.0 nightclub — built without ever opening a level editor." |
| 2 | 0:10–0:20 | **git diff** of the level scrolling | "The level is git-tracked text — every edit a reviewable diff." |
| 3 | 0:20–0:26 | Terminal: 2 real `uedcli` commands (geometry + a light) | "Small verbs compose — geometry, a light, a texture, each one command." |
| 4 | 0:26–0:36 | Terminal: a real `brush measure relation` output | "Every placement is checked against exact geometry, not judged from a screenshot." |
| 5 | 0:36–0:46 | Wireframe build-up timelapse | "The agent builds the club one verified piece at a time." |
| 6 | 0:46–1:11 | **Showcase**: 2 strongest club shots | "Given a prompt, the agent authored this — geometry, textures, lighting, all as text." |
| 7 | 1:11–1:23 | Hold on a hero club frame → title card | "This level was built entirely by AI." → **"uedcli — MIT-licensed, open source."** |

## Decisions locked
- **Cut the colonnade beats** — `mp4.py`'s actual `BEATS` list has been club-only for a while; this
  sheet was stale against it. Fixed here, not just narration-deep.
- **Cut the roadmap beat** — minimalism call; the funding ask/roadmap lives in the written grant
  application, not the video.
- **New measure beat (#4)** replaces two of the four repeated showcase shots. It's the sharpened
  differentiator: exact geometric verification instead of an agent eyeballing a render — stated as
  uedcli's own property, no comparison to any other tool.
- **Showcase trimmed 4 shots → 2** — pick the two strongest club angles once fresh shots exist.

## Asset status
- Done: `out/pitch.mp4` built from `capture-club-shots.sh`'s renders of the rebuilt (measure-driven,
  mitered-corner) club level — no manual screenshot step.
- **Render:** `make mp4` (Pillow slideshow + ffmpeg). This sandbox has no system ffmpeg; a static
  binary via `pip install imageio-ffmpeg` + `FFMPEG=<its path>` works.

## Open
- Club neon sign: de-tile to single logos; replace the DX "Lucky Money" brand with a CC-licensed
  logo (texture-import path TBD).
- Voiceover: TTS for iteration, human VO for the final (captions can carry it if VO slips).
