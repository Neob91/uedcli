#!/usr/bin/env python3
"""Does `FPlane(Light, V[j], V[jPrev])` face the clip poly's interior?

Random convex planar polygons, random light positions on each side of the polygon's WINDING normal.
For every edge it forms the beam plane the editor forms and sums the signed distance of the poly's
own vertices — the quantity the retired `clip_beam` sign-sum heuristic tested. A "flip" is a
negative sum, i.e. an edge where the heuristic would have negated the editor's plane.

Expected (and produced): 0 flips with the light on the plus-winding side — which is the side
`actor_visibility`'s `d < 0` gate always puts it on — and every edge flipped on the minus side.
So the heuristic is inert on well-formed geometry and the two orientations are one thing.
"""
import math
import random


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def run(light_side: int, trials: int = 20000) -> tuple[int, int]:
    """`light_side` +1/-1 = which side of the winding normal the light sits on."""
    flips = edges = 0
    for _ in range(trials):
        n = (random.gauss(0, 1), random.gauss(0, 1), random.gauss(0, 1))
        ln = math.sqrt(dot(n, n))
        n = tuple(x / ln for x in n)
        seed = (1, 0, 0) if abs(n[0]) < 0.9 else (0, 1, 0)
        u = sub(seed, tuple(n[i] * dot(seed, n) for i in range(3)))
        lu = math.sqrt(dot(u, u))
        u = tuple(x / lu for x in u)
        v = cross(n, u)
        base = tuple(random.uniform(-1000, 1000) for _ in range(3))
        # Vertices on a circle at sorted angles => convex, wound about +n.
        k = random.randint(3, 8)
        radius = random.uniform(10, 500)
        poly = [
            tuple(base[i] + radius * math.cos(a) * u[i] + radius * math.sin(a) * v[i] for i in range(3))
            for a in sorted(random.uniform(0, 2 * math.pi) for _ in range(k))
        ]
        height = light_side * random.uniform(1, 500)
        off_u, off_v = random.uniform(-800, 800), random.uniform(-800, 800)
        light = tuple(base[i] + n[i] * height + u[i] * off_u + v[i] * off_v for i in range(3))
        for j in range(k):
            normal = cross(sub(poly[j], light), sub(poly[j - 1], light))
            edges += 1
            if sum(dot(normal, sub(w, light)) for w in poly) < 0:
                flips += 1
    return flips, edges


if __name__ == "__main__":
    random.seed(7)
    for side, label in ((+1, "plus"), (-1, "minus")):
        flips, edges = run(side)
        print(f"light on the {label}-winding side: {flips} flips of {edges} edges")
