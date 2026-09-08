"""Grade a subagent's (or any) trunk against a task oracle. For each actor:
brushes are read as their corner CENTROID (robust to `brush vertex list`'s
corner ordering, and a rigid axis-aligned translation's centroid shift IS
the delta); point actors are read by Location. Classifies every actor as
correct / never touched / touched wrong / (anchors only) anchor itself wrong.
"""
import json, os, pathlib, re, subprocess, sys

WT = "/workspace/uedcli/.claude/worktrees/geom-eval"
PY = "/workspace/uedcli/.venv/bin/python"
EPS = 0.5  # world units tolerance

def _run(project, args):
    env = {**os.environ, "UEDCLI_PROJECT": str(project), "UEDCLI_LEVEL": "unatco"}
    return subprocess.run([PY, "-m", "uedcli", *args], cwd=WT, env=env,
                           capture_output=True, text=True)

def read_corners(project: pathlib.Path, actor: str):
    """Full corner list for a brush, or None if `actor` is a point actor
    (`brush vertex list` exits 0 on a point actor too -- "0 vertices")."""
    r = _run(project, ["brush", "vertex", "list", actor])
    if r.returncode != 0:
        return None
    coords = re.findall(r"\(([-\d.]+),([-\d.]+),([-\d.]+)\)", r.stdout)
    return [(float(a), float(b), float(c)) for a, b, c in coords] or None

def read_position(project: pathlib.Path, actor: str):
    """(x,y,z) -- a brush's corner CENTROID (fine for dependents: they
    translate rigidly, whole shape included), or a point actor's Location.
    NOT used for anchors -- an anchor is resized (only one face moves), so
    its centroid dilutes the real shift; see anchor_delta below."""
    corners = read_corners(project, actor)
    if corners:
        xs, ys, zs = zip(*corners)
        return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
    r = _run(project, ["actor", "prop", "get", actor, "Location"])
    m = re.search(r"X=([-\d.]+),Y=([-\d.]+),Z=([-\d.]+)", r.stdout)
    return tuple(float(v) for v in m.groups())

def anchor_delta(baseline_at_corners, subject_corners):
    """The anchor's ACTUAL delta: for each of the SPECIFIC corners the spec
    names as moving (`at`), nearest-match it in the subject's current corner
    set and average the offsets -- ignoring the anchor's other (fixed)
    corners, which a whole-brush centroid would otherwise dilute against."""
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
    results = []

    for a in oracle["anchors"]:
        subject_corners = read_corners(subject, a["actor"])
        d = anchor_delta([tuple(c) for c in a["at"]], subject_corners)
        ok = close(d, tuple(a["task_delta"]))
        results.append(dict(actor=a["actor"], role="anchor", delta=d, expected=a["task_delta"],
                             verdict="correct" if ok else "anchor_wrong", why=a["why"]))

    anchor_actual_delta = {r["actor"]: r["delta"] for r in results}

    for dep in oracle["dependents"]:
        base_pos = read_position(baseline, dep["actor"])
        sub_pos = read_position(subject, dep["actor"])
        d = sub(sub_pos, base_pos)
        anchor_d = anchor_actual_delta[dep["anchor"]]
        if close(d, (0, 0, 0)):
            verdict = "never_touched"
        elif close(d, anchor_d):
            verdict = "correct"
        else:
            verdict = "touched_wrong"
        results.append(dict(actor=dep["actor"], role=f"dependent(of {dep['anchor']})",
                             delta=d, expected=anchor_d, verdict=verdict, why=dep["why"]))

    for u in oracle["unchanged"]:
        base_pos = read_position(baseline, u["actor"])
        sub_pos = read_position(subject, u["actor"])
        d = sub(sub_pos, base_pos)
        verdict = "correct" if close(d, (0, 0, 0)) else "touched_when_should_not_be"
        results.append(dict(actor=u["actor"], role="unchanged", delta=d, expected=(0, 0, 0),
                             verdict=verdict, why=u["why"]))

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
