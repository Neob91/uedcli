"""Spike: split polys into non-shadowing groups for a fixed perspective.

For a given camera/view, two polys "conflict" if their screen-space projections
overlap (one shadows the other, making a number on one ambiguous with the other).
Greedy graph-coloring over a deterministic poly order partitions the polys so that
within each color group NO two faces overlap on screen. We then render one image per
group: the whole scene as a faint context wireframe, plus THIS group's face numbers
painted opaque on top. Since group members never overlap, every number sits on a
fully-unshadowed face -> unambiguous which face each number labels.

Run:  cd Tools/uedcli && bin/uedcli-py _scratch/polysplit_spike.py
"""
import math
import os
import sys


def _find_pkg_root(start):
    d = os.path.dirname(os.path.abspath(start))
    while d != os.path.dirname(d):
        if os.path.isfile(os.path.join(d, "uedcli", "__init__.py")):
            return d
        d = os.path.dirname(d)
    raise RuntimeError("could not locate the uedcli package root above " + start)


sys.path.insert(0, _find_pkg_root(__file__))

from uedcli import preview as P
from uedcli.builders import cube, cylinder, make_brush_actor
from uedcli.rotation import actor_linear, actor_prepivot, local_offset

OUT = os.environ.get("POLYSPLIT_OUT",
                     os.path.join(_find_pkg_root(__file__), "_scratch", "polysplit"))
os.makedirs(OUT, exist_ok=True)


# ---- projected-poly extraction (mirrors render_brushes_pgm's per-poly loop) ----

class PolyRec:
    __slots__ = ("actor_idx", "poly_idx", "v3", "vs", "front", "depth", "tint", "brush",
                 "is_solid", "plan")

    def __init__(self, actor_idx, poly_idx, v3, vs, front, depth, tint, brush, is_solid):
        self.actor_idx = actor_idx
        self.poly_idx = poly_idx
        self.v3 = v3
        self.vs = vs                    # projected world-2d (pre-pixel)
        self.front = front
        self.depth = depth
        self.tint = tint
        self.brush = brush
        self.is_solid = is_solid
        self.plan = None                # _DecalPlan once the number decal is placed (None = not rendered)


def extract_polys(actors, view, iso_angle=30.0):
    tints = P.assign_tints(actors)
    d_vec = P._view_depth(iso_angle, view)
    recs = []
    for ai, actor in enumerate(actors):
        if actor.brush is None:
            continue
        R = actor_linear(actor)
        prepivot = actor_prepivot(actor)
        loc = actor.location or (0, 0, 0)
        is_solid = P.classify_brush(actor) not in ("subtract", "nonsolid")
        for pi, poly in enumerate(actor.brush.polys):
            v3 = [(float(loc[0] + w[0]), float(loc[1] + w[1]), float(loc[2] + w[2]))
                  for w in (local_offset(R, prepivot, v) for v in poly.vertices)]
            vs = [P._project(p, view, iso_angle) for p in v3]
            if not vs:
                continue
            n = len(vs)
            front = P._is_front(v3, view, iso_angle)
            depth = sum(c * dc for c, dc in zip(
                (sum(p[0] for p in v3) / n, sum(p[1] for p in v3) / n, sum(p[2] for p in v3) / n), d_vec))
            recs.append(PolyRec(ai, pi, v3, vs, front, depth, tints[actor.name], actor.name, is_solid))
    return recs, tints


# ---- pixel framing (mirrors render_brushes_pgm) ----

def make_framing(recs, size, pad=6):
    allpts = [p for r in recs for p in r.vs]
    minx, maxx = min(p[0] for p in allpts), max(p[0] for p in allpts)
    miny, maxy = min(p[1] for p in allpts), max(p[1] for p in allpts)
    span = max(maxx - minx, maxy - miny) or 1.0

    def to_px(p):
        x = int((p[0] - minx) / span * (size - 2 * pad)) + pad
        y = size - 1 - (int((p[1] - miny) / span * (size - 2 * pad)) + pad)
        return x, y

    def to_pxf(p):
        x = (p[0] - minx) / span * (size - 2 * pad) + pad
        y = size - 1 - ((p[1] - miny) / span * (size - 2 * pad) + pad)
        return (x, y)

    return to_px, to_pxf


# ---- decal-bbox overlap (what actually matters: the small centered NUMBERS, not the faces) ----

def rects_overlap(a, b, pad=3.0):
    """True iff decal bounding boxes a,b (px, x0,y0,x1,y1) overlap after growing each by `pad`.
    Two big faces can overlap hugely while their small centered numbers never touch — so the
    conflict is between the NUMBER decals, with a little padding so near-misses still separate."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + pad <= bx0 or bx1 + pad <= ax0 or ay1 + pad <= by0 or by1 + pad <= ay0)


# ---- deterministic greedy coloring over the DECAL-overlap graph ----

def color_groups(recs, bboxes):
    ids = list(range(len(recs)))
    adj = {i: set() for i in ids}
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            if rects_overlap(bboxes[a], bboxes[b]):
                adj[a].add(b)
                adj[b].add(a)
    # Welsh-Powell: color highest-overlap-degree faces first (fewer colors); ties broken by the
    # actor's NAME (a stable identity, NOT the input-list position) + poly index, so the partition
    # is identical regardless of the order actors arrive in — greedy coloring is order-sensitive.
    order = sorted(ids, key=lambda i: (-len(adj[i]), recs[i].brush, recs[i].poly_idx))
    color = {}
    for i in order:
        used = {color[nb] for nb in adj[i] if nb in color}
        c = 0
        while c in used:
            c += 1
        color[i] = c
    ncolors = max(color.values()) + 1 if color else 0
    groups = [[] for _ in range(ncolors)]
    for i in sorted(ids, key=lambda i: (recs[i].brush, recs[i].poly_idx)):
        groups[color[i]].append(i)
    return groups, color


# ---- render one group: faint full wireframe + this group's numbers opaque on top ----

FAINT = (176, 176, 184)


def render_group(all_recs, size, to_px, group_recs):
    buf = P._new_buf(size)
    # faint context: every face's wireframe, so the shape reads
    for r in all_recs:
        px = [to_px(p) for p in r.vs]
        for i in range(len(px)):
            P._line(buf, size, px[i], px[(i + 1) % len(px)], FAINT)
    # this group's faces: bold outline in the brush tint + its already-placed number decal, opaque
    for r in group_recs:
        px = [to_px(p) for p in r.vs]
        for k in range(len(px)):
            P._line(buf, size, px[k], px[(k + 1) % len(px)], r.tint, weight=2)
    for r in group_recs:
        P._draw_painted_decal(buf, size, r.plan, r.tint, alpha=0.95)
    return P._ppm(buf, size)


def write_ppm_png(ppm_bytes, path_png):
    # convert P6 ppm -> PNG via Pillow (dev dep)
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(ppm_bytes))
    img.save(path_png)


def run_scene(name, actors, view="iso", size=384, iso_angle=30.0):
    recs, tints = extract_polys(actors, view, iso_angle)
    to_px, to_pxf = make_framing(recs, size)

    def world_to_pxf(p3):
        return to_pxf(P._project(p3, view, iso_angle))

    # Only faces whose number is ACTUALLY rendered participate: place each decal, drop the ones
    # `_plan_onface_texture` omits (too small in world space -> no number -> nothing to disambiguate).
    rendered = []
    for r in recs:
        plan = P._plan_onface_texture(r.v3, world_to_pxf, str(r.poly_idx))
        if plan is not None:
            r.plan = plan
            rendered.append(r)
    bboxes = [r.plan.bbox() for r in rendered]
    groups, color = color_groups(rendered, bboxes)
    print(f"[{name}] view={view}: {len(recs)} polys ({len(rendered)} numbered) -> {len(groups)} "
          f"groups {[len(g) for g in groups]}")
    from PIL import Image, ImageDraw
    panes = []
    for gi, g in enumerate(groups):
        ppm = render_group(recs, size, to_px, [rendered[i] for i in g])
        import io
        panes.append(Image.open(io.BytesIO(ppm)).convert("RGB"))
        labels = ", ".join(f"{rendered[i].brush}#{rendered[i].poly_idx}" for i in g)
        print(f"    g{gi}: {labels}")
    gap, top = 8, 20
    strip = Image.new("RGB", (size * len(panes) + gap * (len(panes) - 1), size + top), (245, 245, 245))
    d = ImageDraw.Draw(strip)
    for i, im in enumerate(panes):
        x = i * (size + gap)
        strip.paste(im, (x, top))
        d.text((x + 4, 4), f"group {i}", fill=(0, 0, 0))
    strip.save(os.path.join(OUT, f"{name}_{view}_strip.png"))
    return groups


def main():
    room = make_brush_actor("Room", cube(512, 512, 384), location=(0, 0, 0), csg="subtract")
    pillar = make_brush_actor("Pillar", cube(96, 96, 384), location=(0, 0, 0), csg="add")
    run_scene("room", [room], view="iso")
    run_scene("roompillar", [room, pillar], view="iso")
    cyl = make_brush_actor("Cyl", cylinder(256, 128, sides=8), location=(0, 0, 0), csg="add")
    cube_a = make_brush_actor("Box", cube(160, 160, 160), location=(300, 0, 0), csg="add")
    run_scene("cubecyl", [cube_a, cyl], view="iso")


if __name__ == "__main__":
    main()
