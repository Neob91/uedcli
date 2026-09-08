"""Grade a subagent's (or any) trunk against a task oracle (spec.py's flat
`entries` list). Dispatches on `kind`:

  update (target="corners")   -- specific named corners must have moved by
                                   an ABSOLUTE `delta` (a task-pinned value).
  update (target="unchanged") -- must equal the baseline exactly.
  anchor                      -- must match its named anchor's ACTUAL delta
                                   in the SAME subject trunk (not a hardcoded
                                   number) -- computed from `update` entries
                                   processed first.
  create/delete                -- documented in spec.py, not yet implemented;
                                   raises NotImplementedError if the oracle
                                   ever contains one (add real handling only
                                   when a task needs it).

Brushes are read as their corner CENTROID for `anchor`/unchanged checks
(fine: they translate rigidly, whole shape included); an `update` with
target="corners" instead nearest-matches the SPECIFIC named corners, since
that kind of entry RESIZES the brush (only one face moves) and a centroid
would dilute the real shift by however much of the brush stayed fixed.

LIMIT (not yet needed by either current task, so not built): `anchor` only
ever compares position (Location, or a brush's corners) -- a future task
needing "this fixture must ROTATE with its anchor" would silently misgrade
(a Rotation-only change reads as delta (0,0,0) -> never_touched) rather than
raising, unlike create/delete which fail loud. Extend read_position (or add
a parallel read_rotation) when a real task needs a rotation-anchor.
"""
import json, os, pathlib, re, subprocess, sys

WT = "/workspace/uedcli/.claude/worktrees/geom-eval"
PY = "/workspace/uedcli/.venv/bin/python"
EPS = 0.5  # world units tolerance

class ActorMissing(Exception):
    """`actor` doesn't exist in `project` -- a real, plausible subagent
    failure mode (deleted/renamed the wrong thing), not a script bug."""
    def __init__(self, project, actor):
        self.project, self.actor = project, actor
        super().__init__(f"actor not found: {actor} (in {project})")

def _run(project, args):
    env = {**os.environ, "UEDCLI_PROJECT": str(project), "UEDCLI_LEVEL": "unatco"}
    return subprocess.run([PY, "-m", "uedcli", *args], cwd=WT, env=env,
                           capture_output=True, text=True)

def _actor_exists(project: pathlib.Path, actor: str) -> bool:
    r = _run(project, ["actor", "prop", "get", actor, "Location"])
    return not (r.returncode != 0 and "Actor not found" in r.stderr + r.stdout)

def read_corners(project: pathlib.Path, actor: str):
    """Full corner list for a brush, or None if `actor` is a point actor
    (`brush vertex list` exits 0 on a point actor too -- "0 vertices").
    Raises ActorMissing if `actor` doesn't exist at all in `project`."""
    r = _run(project, ["brush", "vertex", "list", actor])
    if r.returncode != 0:
        if not _actor_exists(project, actor):
            raise ActorMissing(project, actor)
        return None
    coords = re.findall(r"\(([-\d.]+),([-\d.]+),([-\d.]+)\)", r.stdout)
    return [(float(a), float(b), float(c)) for a, b, c in coords] or None

def read_position(project: pathlib.Path, actor: str):
    """(x,y,z) -- a brush's corner centroid, or a point actor's Location.
    Raises ActorMissing if `actor` doesn't exist at all in `project`."""
    corners = read_corners(project, actor)
    if corners:
        xs, ys, zs = zip(*corners)
        return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
    r = _run(project, ["actor", "prop", "get", actor, "Location"])
    if r.returncode != 0:
        raise ActorMissing(project, actor)
    m = re.search(r"X=([-\d.]+),Y=([-\d.]+),Z=([-\d.]+)", r.stdout)
    return tuple(float(v) for v in m.groups())

def named_corners_delta(baseline_at_corners, subject_corners):
    """For each of the SPECIFIC corners an `update(target="corners")` entry
    names, nearest-match it in the subject's current corner set and average
    the offsets -- ignoring the brush's other (fixed) corners."""
    offsets = []
    for c in baseline_at_corners:
        nearest = min(subject_corners, key=lambda s: sum((a - b) ** 2 for a, b in zip(s, c)))
        offsets.append(tuple(n - b for n, b in zip(nearest, c)))
    return tuple(sum(vals) / len(vals) for vals in zip(*offsets))

def sub(a, b):
    return tuple(round(x - y, 3) for x, y in zip(a, b))

def close(a, b, eps=EPS):
    return all(abs(x - y) <= eps for x, y in zip(a, b))

def check_trunk(oracle_path: pathlib.Path, baseline: pathlib.Path, subject: pathlib.Path):
    oracle = json.loads(oracle_path.read_text())
    entries = oracle["entries"]
    results = []
    anchor_actual_delta = {}

    # pass 1: `update` entries (anchors' own absolute targets are among these)
    for e in entries:
        if e["kind"] != "update":
            continue
        try:
            if e.get("target") == "corners":
                subject_corners = read_corners(subject, e["actor"])
                d = named_corners_delta([tuple(c) for c in e["at"]], subject_corners)
                ok = close(d, tuple(e["delta"]))
                results.append(dict(actor=e["actor"], role="update(corners)", delta=d, expected=e["delta"],
                                     verdict="correct" if ok else "wrong", why=e["why"]))
                anchor_actual_delta[e["actor"]] = d
            elif e.get("target") == "unchanged":
                base_pos = read_position(baseline, e["actor"])
                sub_pos = read_position(subject, e["actor"])
                d = sub(sub_pos, base_pos)
                verdict = "correct" if close(d, (0, 0, 0)) else "touched_when_should_not_be"
                results.append(dict(actor=e["actor"], role="update(unchanged)", delta=d, expected=(0, 0, 0),
                                     verdict=verdict, why=e["why"]))
            else:
                raise NotImplementedError(f"update target {e.get('target')!r} not implemented: {e}")
        except ActorMissing as ex:
            # A very plausible subagent failure mode (deleted/renamed the wrong
            # thing while editing) -- classify it, don't crash the whole run.
            results.append(dict(actor=e["actor"], role=f"update({e.get('target')})", delta=None, expected=None,
                                 verdict="missing", why=e["why"]))

    # pass 2: `anchor` entries (need pass 1's actual deltas)
    for e in entries:
        if e["kind"] != "anchor":
            continue
        if e["to"] not in anchor_actual_delta:
            # Its own anchor was missing/unresolved (pass 1 already reported that) --
            # nothing sensible to compare against, so this one is unresolvable too.
            results.append(dict(actor=e["actor"], role=f"anchor(to {e['to']})", delta=None, expected=None,
                                 verdict="anchor_unresolved", why=e["why"]))
            continue
        try:
            base_pos = read_position(baseline, e["actor"])
            sub_pos = read_position(subject, e["actor"])
        except ActorMissing:
            results.append(dict(actor=e["actor"], role=f"anchor(to {e['to']})", delta=None, expected=None,
                                 verdict="missing", why=e["why"]))
            continue
        d = sub(sub_pos, base_pos)
        anchor_d = anchor_actual_delta[e["to"]]
        if close(d, (0, 0, 0)):
            verdict = "never_touched"
        elif close(d, anchor_d):
            verdict = "correct"
        else:
            verdict = "touched_wrong"
        results.append(dict(actor=e["actor"], role=f"anchor(to {e['to']})", delta=d, expected=anchor_d,
                             verdict=verdict, why=e["why"]))

    for e in entries:
        if e["kind"] in ("create", "delete"):
            raise NotImplementedError(f"{e['kind']} entries are documented but not yet implemented: {e}")
        if e["kind"] not in ("update", "anchor"):
            raise ValueError(f"unknown entry kind {e['kind']!r}: {e}")

    return results

if __name__ == "__main__":
    oracle_path, baseline, subject = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
    results = check_trunk(oracle_path, baseline, subject)
    n_bad = sum(1 for r in results if r["verdict"] != "correct")
    for r in results:
        mark = "OK " if r["verdict"] == "correct" else "FAIL"
        print(f"{mark} {r['actor']:20} {r['role']:22} delta={r['delta']} expected={r['expected']} -> {r['verdict']}")
        if r["verdict"] != "correct":
            # Grading cares about outcome, not method: a mechanical FAILURE isn't
            # necessarily wrong -- surface the intent so a reviewer can judge
            # whether it was satisfied some other way this check didn't anticipate.
            print(f"     intent: {r['why']}")
    print(f"\n{len(results)-n_bad}/{len(results)} correct")
    if n_bad:
        print(f"{n_bad} failure(s) above need review against their stated intent, not an automatic fail.")
    sys.exit(1 if n_bad else 0)
