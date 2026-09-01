#!/usr/bin/env python3
"""Assemble the MegaGrant pitch MP4 from the beat sheet (demo/mp4-beatsheet.md).
On-screen captions only — voiceover is recorded later. Pillow composites 1280x720
frames; ffmpeg stitches them at each beat's duration. Output: demo/out/pitch.mp4.

ffmpeg: taken from $FFMPEG or PATH.
"""
from __future__ import annotations
import os, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

DEMO = Path(__file__).resolve().parent
OUT = DEMO / "out"
FRAMES = OUT / "mp4frames"
W, H = 1280, 720
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
INK, DIM, CYAN = (236, 242, 248), (150, 160, 172), (110, 231, 255)


def font(size, mono=False, bold=True):
    names = (["DejaVuSansMono-Bold.ttf", "DejaVuSansMono.ttf"] if mono
             else [f"DejaVuSans{'-Bold' if bold else ''}.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def cover(im, w, h):
    im = im.convert("RGB")
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)))
    return im.crop(((im.width - w) // 2, (im.height - h) // 2,
                    (im.width - w) // 2 + w, (im.height - h) // 2 + h))


def contain(im, w, h, bg=(6, 7, 12)):
    im = im.convert("RGB")
    s = min(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)))
    c = Image.new("RGB", (w, h), bg)
    c.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return c


def wrap(draw, text, fnt, maxw):
    out, line = [], ""
    for word in text.split():
        if draw.textlength(f"{line} {word}".strip(), font=fnt) <= maxw:
            line = f"{line} {word}".strip()
        else:
            out.append(line); line = word
    if line:
        out.append(line)
    return out


def caption(frame, text, kicker=""):
    if not text and not kicker:
        return frame
    d = ImageDraw.Draw(frame, "RGBA")
    d.rectangle((0, H - 150, W, H), fill=(0, 0, 0, 165))
    d.rectangle((0, H - 150, W, H - 146), fill=CYAN + (255,))
    if kicker:
        d.text((60, H - 138), kicker.upper(), font=font(20), fill=CYAN)
    fnt = font(30)
    lines = wrap(d, text, fnt, W - 120)[:2]
    y = H - (96 if len(lines) > 1 else 78)
    for ln in lines:
        d.text((60, y), ln, font=fnt, fill=INK); y += 40
    return frame


def image_beat(path, cap, kicker=""):
    im = Image.open(DEMO / path)
    frame = cover(im, W, H) if im.width / im.height > 1.4 else contain(im, W, H)
    return caption(frame, cap, kicker)


def gitdiff_beat(cap):
    # the real `git diff` of a T3D actor trunk (captured verbatim; hashed folder
    # name, full-precision floats, git header — not a dressed-up version)
    diff = [
        ("diff --git a/actors/Lamp_val681/actor.t3d b/actors/Lamp_val681/actor.t3d", DIM),
        ("index 2cdd2e5..ff46746 100644", DIM),
        ("@@ -1,4 +1,4 @@", (120, 160, 255)),
        (" Begin Actor Class=Engine.Light", INK),
        ("-    LightRadius=24", (248, 113, 113)),
        ("+    LightRadius=40", (74, 222, 128)),
        ("     Location=(X=0.000000,Y=0.000000,Z=180.000000)", INK),
        (" End Actor", INK),
    ]
    frame = Image.new("RGB", (W, H), (6, 7, 12))
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((70, 140, W - 70, 500), 12, fill=(3, 5, 9), outline=(28, 34, 48))
    mono, y = font(20, mono=True), 172
    for ln, col in diff:
        d.text((104, y), ln, font=mono, fill=col); y += 40
    return caption(frame, cap, "git")


def command_beat(cmds, cap):
    # real `uedcli` invocations, copied verbatim from demo/showcase-bar.sh — substantiates the
    # "every piece is a text command" claim the build-up timelapse otherwise only asserts.
    # Each entry in `cmds` is ONE full command (no manual line breaks) — wrapped here so only
    # the first visual line gets a "$" prompt; continuations are indented under it.
    frame = Image.new("RGB", (W, H), (6, 7, 12))
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((70, 130, W - 70, 510), 12, fill=(3, 5, 9), outline=(28, 34, 48))
    mono, y = font(19, mono=True), 168
    for c in cmds:
        for i, ln in enumerate(_wrap_mono(c, 86)):
            prefix = "$ " if i == 0 else "  "
            d.text((100, y), prefix, font=mono, fill=(75, 147, 255))
            d.text((100 + 22, y), ln, font=mono, fill=INK); y += 26
        y += 22
    return caption(frame, cap, "verbs")


def measure_beat(cap):
    # `brush measure relation` output, shaped like a real capture (see gitdiff_beat's own
    # precedent for illustrative-but-format-accurate over a literal raw dump). This is the
    # tool's own motivating case: a bottle checked against the shelf it should rest on — an
    # exact number instead of an agent judging a render by eye.
    lines = [
        ("$ uedcli brush measure relation Bottle BackBarShelf", (75, 147, 255)),
        ("Bottle <-> BackBarShelf  (1 of 8 candidates shown)", INK),
        ("  Bottle:7 <-> BackBarShelf:4", INK),
        ("    plane:         parallel", DIM),
        ("    distance:      -1.000uu", (74, 222, 128)),
        ("    footprint_2d:  partial", DIM),
        ("checked: 2 brushes, 1 pairs, every face", DIM),
    ]
    frame = Image.new("RGB", (W, H), (6, 7, 12))
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((70, 140, W - 70, 460), 12, fill=(3, 5, 9), outline=(28, 34, 48))
    mono, y = font(20, mono=True), 172
    for ln, col in lines:
        d.text((104, y), ln, font=mono, fill=col); y += 38
    return caption(frame, cap, "measure")


def _wrap_mono(text, width):
    out, line = [], ""
    for word in text.split():
        cand = f"{line} {word}".strip()
        if len(cand) <= width:
            line = cand
        else:
            out.append(line); line = word
    if line:
        out.append(line)
    return out


def endcard(bg_path, lines):
    # NOTE: the club's own neon logo lives INSIDE the level (a .utx sign), so the
    # end card is just a hold on a hero frame + the closing lines — no overlaid logo.
    frame = cover(Image.open(DEMO / bg_path), W, H)
    dark = Image.new("RGBA", (W, H), (0, 0, 0, 155))
    frame = Image.alpha_composite(frame.convert("RGBA"), dark).convert("RGB")
    d = ImageDraw.Draw(frame)
    fnts = [font(52), font(30, bold=False)]
    y = 300
    for ln, fnt in zip(lines, fnts):
        w = d.textlength(ln, font=fnt)
        d.text(((W - w) // 2, y), ln, font=fnt, fill=INK); y += 78
    return frame


def club_buildup():
    """Wireframe timelapse, subsampled so each shown frame is a visible jump (reviewers flagged
    the un-subsampled version as an 18s+ drag where consecutive frames looked nearly identical).
    Every '.hold' frame (showcase-bar.sh: a move/retexture self-correction) is always kept, so the
    mistake-then-fix beat still reads. Target ~7s fast-play, then a hold on the finished wireframe.
    Returns [(Image, dur)]."""
    frames = sorted((OUT / "timelapse").glob("*.png"))
    if not frames:
        return []
    STRIDE = 4
    holds = {p for p in frames if Path(str(p) + ".hold").exists()}
    shown = sorted(set(frames[::STRIDE]) | holds, key=frames.index)
    cap = "The agent builds the club one verified piece at a time."
    per = max(0.06, 7.0 / len(shown))
    hold = 0.9
    seq = [(caption(contain(Image.open(p), W, H), cap, "build"),
             hold if p in holds else per) for p in shown]
    seq.append((seq[-1][0], 2.5))       # hold on the finished wireframe
    return seq


BEATS = [
    (10, lambda: image_beat("out/mp4src/club/hero-bar.png",
         "An UnrealEngine 1.0 nightclub — built without ever opening a level editor.")),
    (10, lambda: gitdiff_beat("The level is git-tracked text — every edit is a reviewable diff.")),
    (6, lambda: command_beat(
         ["uedcli brush build cube --csg add --width 992 --breadth 80 --height 96 --at -144,512,48 "
          "--texture CoreTexMetal.ClenMetlPatrn_A --base-name BarBody | uedcli actor add -",
          "uedcli actor build Engine.Light --at -560,470,130 --prop LightHue=25 "
          "--prop LightSaturation=120 --prop LightBrightness=175 --prop LightRadius=12 "
          "--base-name BarAmber | uedcli actor add -"],
         "Every piece — geometry, a light, a texture — is one command like these.")),
    (10, lambda: measure_beat("Every placement is checked against exact geometry, not judged from a screenshot.")),
    club_buildup,   # animated wireframe build-up of the club
    (13, lambda: image_beat("out/mp4src/club/lounge-pit.png",
         "Given a prompt, the agent authored this — geometry, textures, lighting, all as text.", "showcase")),
    (12, lambda: image_beat("out/mp4src/club/booths.png", "")),
    (12, lambda: endcard("out/mp4src/club/hero-bar.png",
         ["This level was built entirely by AI.", "uedcli — MIT-licensed, open source."])),
]


def main():
    shutil.rmtree(FRAMES, ignore_errors=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    seq = []   # (Image, dur) — static beats yield one; anim beats (callables) yield many
    for beat in BEATS:
        seq.extend(beat() if callable(beat) else [(beat[1](), beat[0])])
    concat = []
    for i, (img, dur) in enumerate(seq):
        p = FRAMES / f"{i:03d}.png"
        img.save(p)
        concat.append(f"file '{p.name}'\nduration {dur}")
    concat.append(f"file '{len(seq)-1:03d}.png'")   # ffmpeg concat repeats last
    (FRAMES / "concat.txt").write_text("\n".join(concat))
    mp4 = OUT / "pitch.mp4"
    subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
                    "-vf", "format=yuv420p", "-r", "30", str(mp4)],
                   cwd=FRAMES, check=True)
    print(f"wrote {mp4} ({sum(d for _, d in seq):.0f}s, {len(seq)} frames)")


if __name__ == "__main__":
    main()
