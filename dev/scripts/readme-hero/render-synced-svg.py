#!/usr/bin/env python3
"""Assemble the synced README hero SVG from rendered frames + the pipeline's names.

Usage: render-synced-svg.py FRAMEDIR ROOM COL1 COL2 OUT.svg
Called by build-hero.sh. FRAMEDIR holds x1.png..x11.png (one per pipeline step);
ROOM/COL1/COL2 are the actor names the pipeline assigned, echoed into the shown
commands so the terminal text matches what was actually run.

Left panel: a terminal revealing each command. Right panel: the level's
`actor diagram` render after that command. Both are driven off one looping
timeline, so they stay in sync. The corner-clip phase is compressed 2.5x.
"""
import base64, sys, html

FRAMES, ROOM, COL1, COL2, OUT = sys.argv[1:6]
DUR = 36  # seconds, looping

def b64(name):
    with open(f"{FRAMES}/{name}.png", "rb") as f:
        return base64.b64encode(f.read()).decode()

# (appear%, frame)  — clip steps (x2..x5) compressed 2.5x; later steps shifted earlier
frames = [(6,"x1"),(12,"x2"),(14.4,"x3"),(16.8,"x4"),(19.2,"x5"),(27,"x6"),(35,"x7"),(43,"x8"),(51,"x9"),(59,"x10"),(67,"x11")]
frames = [(p, b64(n)) for p, n in frames]

# (appear%, kind, text). Keep these in lockstep with build-hero.sh's commands.
rows = [
    (2,   "comment", "# two rooms + a corridor, columns turned 45° — built from commands"),
    (6,   "cmd",  "uedcli brush build cube --width 640 --breadth 640 --height 320 --csg subtract --at 0,0,160 \\"),
    (6,   "cont", "| uedcli actor add -                          # a room"),
    (12,  "cmd",  f"uedcli actor show {ROOM} | uedcli brush clip - --plane 160,320,160 1,1,0 --keep below \\"),
    (12,  "cont", f"| uedcli brush replace {ROOM} -          # slice corner 1 at 45°"),
    (14.4,"cmd",  f"uedcli actor show {ROOM} | uedcli brush clip - --plane -160,320,160 -1,1,0 --keep below \\"),
    (14.4,"cont", f"| uedcli brush replace {ROOM} -          # corner 2"),
    (16.8,"cmd",  f"uedcli actor show {ROOM} | uedcli brush clip - --plane 160,-320,160 1,-1,0 --keep below \\"),
    (16.8,"cont", f"| uedcli brush replace {ROOM} -          # corner 3"),
    (19.2,"cmd",  f"uedcli actor show {ROOM} | uedcli brush clip - --plane -160,-320,160 -1,-1,0 --keep below \\"),
    (19.2,"cont", f"| uedcli brush replace {ROOM} -          # corner 4"),
    (27,  "cmd",  "uedcli brush build cube --width 640 --breadth 200 --height 320 --csg subtract --at 640,0,160 \\"),
    (27,  "cont", "| uedcli actor add -                          # corridor, same height"),
    (35,  "cmd",  f"uedcli actor duplicate {ROOM} --by 1280,0,0   # duplicate room, far end"),
    (43,  "cmd",  "uedcli brush build cube --width 120 --breadth 120 --height 320 --solidity semisolid --at 0,0,160 \\"),
    (43,  "cont", "| uedcli actor add -                          # column, room 1"),
    (51,  "cmd",  "uedcli brush build cube --width 120 --breadth 120 --height 320 --solidity semisolid --at 1280,0,160 \\"),
    (51,  "cont", "| uedcli actor add -                          # column, room 2"),
    (59,  "cmd",  f"uedcli actor prop set {COL1} Rotation.Yaw=8192   # turn column 1 in place (45°)"),
    (67,  "cmd",  f"uedcli actor prop set {COL2} Rotation.Yaw=8192   # column 2"),
    (76,  "cmd",  "uedcli actor diagram --view iso --out level.png"),
    (81,  "out",  "wrote level.png"),
]

FONT = 11; LH = 18
TX, TY, TW, TH = 16, 16, 700, 600
IX, IY, IS = 732, 16, 600
W, H = IX + IS + 16, 632
CONT_INDENT = 22
GREEN = "#7ee787"; FG = "#cdd3de"; DIM = "#6b7280"; WHITE = "#ffffff"
prompt = "❯"
CUR_P = 81

def esc(s): return html.escape(s, quote=True)
def kn(p): return "a" + str(p).replace('.', '_')     # CSS-safe keyframe/class name
def split_comment(t):
    i = t.find("  #")
    return (t, "") if i == -1 else (t[:i], t[i:])

pcts = sorted({p for p, *_ in rows} | {p for p, _ in frames} | {CUR_P})
css = ["text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace}", ".rev{opacity:0}"]
for p in pcts:
    snap = max(p - 0.3, 0)
    css.append(f"@keyframes {kn(p)}{{0%,{snap}%{{opacity:0}}{p}%,100%{{opacity:1}}}}")
    css.append(f".{kn(p)}{{animation:{kn(p)} {DUR}s linear infinite}}")
css.append("@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}.cur{animation:blink 1s steps(1) infinite}")

s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-size="{FONT}">',
     f"<style>{''.join(css)}</style>",
     f'<rect x="0" y="0" width="{W}" height="{H}" rx="12" fill="#0d1117"/>',
     f'<rect x="{TX}" y="{TY}" width="{TW}" height="{TH}" rx="9" fill="#161b22" stroke="#30363d"/>',
     f'<rect x="{TX}" y="{TY}" width="{TW}" height="30" rx="9" fill="#20262e"/>',
     f'<rect x="{TX}" y="{TY+18}" width="{TW}" height="12" fill="#20262e"/>']
for i, col in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
    s.append(f'<circle cx="{TX+18+i*18}" cy="{TY+15}" r="5" fill="{col}"/>')
s.append(f'<text x="{TX+TW/2}" y="{TY+19}" text-anchor="middle" fill="#8b949e" font-size="12">uedcli</text>')

y0 = TY + 52
xbase = TX + 16
for i, (p, kind, text) in enumerate(rows):
    y = y0 + i * LH
    if kind in ("cmd", "cont"):
        xx = xbase if kind == "cmd" else xbase + CONT_INDENT
        code, com = split_comment(text.lstrip() if kind == "cont" else text)
        inner = (f'<tspan fill="{GREEN}">{prompt} </tspan>' if kind == "cmd" else "") + f'<tspan fill="{FG}">{esc(code)}</tspan>'
        if com: inner += f'<tspan fill="{DIM}">{esc(com)}</tspan>'
        s.append(f'<g class="rev {kn(p)}"><text x="{xx}" y="{y}">{inner}</text></g>')
    elif kind == "comment":
        s.append(f'<g class="rev {kn(p)}"><text x="{xbase}" y="{y}" fill="{DIM}">{esc(text)}</text></g>')
    elif kind == "out":
        s.append(f'<g class="rev {kn(p)}"><text x="{xbase}" y="{y}" fill="{WHITE}" font-weight="bold">{esc(text)}</text></g>')
cy = y0 + len(rows) * LH
s.append(f'<g class="rev {kn(CUR_P)}"><text x="{xbase}" y="{cy}"><tspan fill="{GREEN}">{prompt} </tspan><tspan class="cur" fill="{FG}">█</tspan></text></g>')

s.append(f'<rect x="{IX}" y="{IY}" width="{IS}" height="{IS}" rx="9" fill="#3f3f3f" stroke="#30363d"/>')
for p, data in frames:
    s.append(f'<g class="rev {kn(p)}"><image x="{IX}" y="{IY}" width="{IS}" height="{IS}" href="data:image/png;base64,{data}"/></g>')
s.append("</svg>")
with open(OUT, "w") as f:
    f.write("".join(s))
print("wrote", OUT)
