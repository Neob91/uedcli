"""The bounded-neighborhood truncation regression.

The whole csg tier rests on one claim: a CSG operation changes the world's solid/void labelling only
inside its own brush volume, so solving over `{brushes whose AABB meets the surveyed actor's region}`
reproduces, inside that region, exactly what the full-level solve produces
(`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/spike.md` §4). The spike measured that
over 140 surveys of real levels; this is the committed version, on a synthetic level small enough to
solve whole.

Two checks, matching what the spike itself compared: the FACT SET must be identical, and the face
signature inside the region must agree by owner and area (never by poly index or face count — a
different tree shape splits the same surface differently, which is not a divergence).
"""
from __future__ import annotations

import dataclasses

import pytest

from uedcli import actor_survey
from uedcli.preview_native import solve_world_probe
from uedcli.tests import survey_scenarios as scen

pytest.importorskip("uedcli_native")


def _whole_level_context(sc, name):
    """The same `SurveyContext`, but solved over EVERY brush in the level instead of the bounded
    neighborhood. `near`/`points` stay as they are — the truncation claim is about the SOLVE, not
    about which actors a fact may name. `seed` carries over unchanged, correctly: it names the
    LEVEL's first world-CSG brush, which is the same brush in both solves."""
    ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
    everything = [sc.level.actors[n] for n in sc.level.order
                  if sc.level.actors[n].brush is not None]
    probe = solve_world_probe(everything, sc.index)
    return dataclasses.replace(ctx, neighbors=everything, probe=probe,
                               faces=actor_survey.csg_faces(probe, ctx.region))


def _key(facts):
    return sorted((f.src, f.dst, f.relation) for f in facts)


def _clip_to_halfspace(poly, axis, limit, keep_below):
    """Clip a 3-D convex polygon by one axis-aligned half-space. Ported verbatim from
    `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/bounded_cost.py`."""
    out = []
    for i in range(len(poly)):
        cur, prev = poly[i], poly[i - 1]
        cur_in = (cur[axis] <= limit) if keep_below else (cur[axis] >= limit)
        prev_in = (prev[axis] <= limit) if keep_below else (prev[axis] >= limit)
        if cur_in != prev_in:
            t = (limit - prev[axis]) / (cur[axis] - prev[axis])
            out.append(tuple(prev[k] + t * (cur[k] - prev[k]) for k in range(3)))
        if cur_in:
            out.append(cur)
    return out


def _clip_to_box(poly, lo, hi):
    for axis in range(3):
        poly = _clip_to_halfspace(poly, axis, hi[axis], True)
        if not poly:
            return []
        poly = _clip_to_halfspace(poly, axis, lo[axis], False)
        if not poly:
            return []
    return poly


def _signature(ctx):
    """Total CLIPPED surface area per owner inside the survey region.

    Summed over `ctx.probe.world_surfaces` — EVERY surviving fragment — and deliberately not over
    `ctx.faces`, which holds one arbitrary representative fragment per (owner, plane). Two solves
    that split the same surface differently pick different representatives with different areas, so
    summing `ctx.faces` would report a different BSP split as a divergence, which is precisely what
    this comparison exists NOT to do. Clipping every fragment to the region and accumulating per
    owner is `bounded_cost.py`'s own `face_signature` technique, minus its poly-index half (the csg
    tier names no poly index).
    """
    lo, hi = (tuple(float(c) for c in ctx.region[0]), tuple(float(c) for c in ctx.region[1]))
    out: dict = {}
    for surf in ctx.probe.world_surfaces:
        if surf.actor is None:
            continue
        clipped = _clip_to_box([tuple(float(c) for c in v) for v in surf.world_verts], lo, hi)
        if len(clipped) < 3:
            continue
        area = actor_survey.poly_area(clipped)
        if area <= 1e-9:
            continue
        out[surf.actor.name] = out.get(surf.actor.name, 0.0) + area
    return out


@pytest.mark.parametrize("name", ["Probe", "Room", "Pillar4"])
def test_the_bounded_solve_and_the_whole_level_solve_agree_on_the_fact_set(name):
    sc = scen.truncation_probe_level()
    bounded = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
    whole = _whole_level_context(sc, name)
    assert len(whole.neighbors) > len(bounded.neighbors), "the neighborhood is a real subset"
    assert _key(actor_survey.csg_facts_for(bounded)) == \
        _key(actor_survey.csg_facts_for(whole))


def test_the_face_signature_inside_the_region_agrees_by_owner_and_area():
    """Compared by (owner, total clipped area), never by polygon identity or face count — the
    spike's own method, and the reason it works: a different BSP split of the same surface is not a
    divergence (spike.md §4, 'The empirical check'). `_signature` sums EVERY surviving fragment
    clipped to the region, not `ctx.faces`'s one representative per plane, which is what makes that
    true."""
    sc = scen.truncation_probe_level()
    bounded = actor_survey.build_context(sc.level, sc.index, "Probe", sc.defaults)
    whole = _whole_level_context(sc, "Probe")
    a, b = _signature(bounded), _signature(whole)
    assert set(a) == set(b)
    for owner in a:
        assert a[owner] == pytest.approx(b[owner], rel=1e-4)


def test_dropping_the_first_world_csg_brush_really_does_change_the_answer():
    """The first-brush clause is load-bearing, not cosmetic: `bsp_brush_csg` SEEDS a leading
    `CSG_Add` as the world shell rather than classifying it, so truncating it away fires that
    shortcut on a different brush. This asserts the mechanism is still live — if it ever stops
    mattering, the clause can be revisited, and this test going green-by-accident would hide that.
    """
    sc = scen.truncation_probe_level()
    ctx = actor_survey.build_context(sc.level, sc.index, "Probe", sc.defaults)
    assert ctx.seed == "Shell"            # the first CONTRIBUTING brush, not trunk index 0
    without_shell = [a for a in ctx.neighbors if a.name != "Shell"]
    probe = solve_world_probe(without_shell, sc.index)
    seeded = {f.owner for f in actor_survey.csg_faces(ctx.probe, ctx.region)}
    unseeded = {f.owner for f in actor_survey.csg_faces(probe, ctx.region)}
    assert seeded != unseeded
