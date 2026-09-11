"""Low-level uedcli-driving helpers shared by render_before (render_manual.py),
extract_execution.py, and render_execution.py: running uedcli against a project,
querying actor existence/order, computing a shared frame, and rendering a quad
diagram (live, or composited with one actor reinserted from another project).
"""
import hashlib, os, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from build_gold import WT, PY

FRAME_PAD = 64

def fingerprint(project: pathlib.Path, level: str) -> str:
    """sha256 over the sorted "relpath\\0content-sha256" lines of every file under
    maps/<level>/actors/ -- identifies the exact base-trunk actor content a diff.patch
    was computed against (extract_execution.py) or is being applied onto
    (render_execution.py), so a drifted base-trunk cache is a clear error, not a
    silent mis-apply."""
    actors_dir = project / "maps" / level / "actors"
    lines = []
    for p in sorted(actors_dir.rglob("*")):
        if p.is_file():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            lines.append(f"{p.relative_to(actors_dir)}\0{digest}")
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()

def run(project, level, args, **kw):
    env = {**os.environ, "UEDCLI_PROJECT": str(project), "UEDCLI_LEVEL": level}
    return subprocess.run([PY, "-m", "uedcli", *args], cwd=WT, env=env,
                           capture_output=True, text=True, **kw)

def actor_exists(project: pathlib.Path, level: str, actor: str) -> bool:
    r = run(project, level, ["actor", "prop", "get", actor, "Location"])
    return not (r.returncode != 0 and "Actor not found" in r.stderr + r.stdout)

def show(project, level, names):
    """`actor show` block for `names` (possibly empty -> "")."""
    if not names:
        return ""
    r = run(project, level, ["actor", "show", "-"], input="\n".join(names))
    r.check_returncode()
    return r.stdout

_BBOX_RE = re.compile(r"min\s+([-\d.]+),([-\d.]+),([-\d.]+)\s*\n\s*max\s+([-\d.]+),([-\d.]+),([-\d.]+)")

def _bbox_union_call(project, level, actors):
    """Union bbox over `actors` in `project`, via ONE `actor bbox` call --
    it already unions a multi-actor set itself, so this is ~1.5s regardless
    of set size, vs ~1.5s PER ACTOR calling it one at a time (measured: a
    35-actor frame went from 100s+ to a couple of seconds). `actor bbox`
    errors hard if ANY name doesn't exist in `project`, so on failure this
    falls back to filtering out the missing ones first (a genuinely created
    or deleted actor won't exist in one of the two trunks) and retrying."""
    if not actors:
        return None
    r = run(project, level, ["actor", "bbox", *actors])
    if r.returncode != 0:
        existing = [a for a in actors if actor_exists(project, level, a)]
        if not existing:
            return None
        r = run(project, level, ["actor", "bbox", *existing])
        if r.returncode != 0:
            return None
    m = _BBOX_RE.search(r.stdout)
    if not m:
        return None
    x0, y0, z0, x1, y1, z1 = map(float, m.groups())
    return (x0, y0, z0), (x1, y1, z1)

def frame_from_actors(projects, level, actors, pad):
    """A `--frame` string: the union bbox of `actors` across every project in
    `projects` (an actor missing from one project just contributes nothing
    from that one), padded by `pad` on every side. None if none of the
    actors exist in any project."""
    boxes = [b for p in projects if (b := _bbox_union_call(p, level, actors)) is not None]
    if not boxes:
        return None
    x0 = min(b[0][0] for b in boxes) - pad
    y0 = min(b[0][1] for b in boxes) - pad
    z0 = min(b[0][2] for b in boxes) - pad
    x1 = max(b[1][0] for b in boxes) + pad
    y1 = max(b[1][1] for b in boxes) + pad
    z1 = max(b[1][2] for b in boxes) + pad
    return ",".join(str(round(v, 2)) for v in (x0, y0, z0, x1, y1, z1))

def scene_names(project, level, frame):
    r = run(project, level, ["actor", "find", "--overlapping-bbox", frame])
    r.check_returncode()
    return r.stdout.split()

def diagram_live_names(project, level, names, frame, highlight, out_path):
    names = list(names)
    # --overlapping-bbox tests each actor's own bbox against `frame`; a
    # point actor mounted slightly proud of a wall (e.g. a light sconce) can
    # sit just outside it and get dropped -- always keep the highlight
    # target in the render set regardless, or --highlight has nothing to
    # highlight and the whole call errors.
    if highlight and highlight not in names:
        names.append(highlight)
    args = ["actor", "diagram", *names,
            "--layout", "quad", "--faces", "wire", "--brush-colors", "csg",
            "--frame", frame, "--size", "1800", "--out", str(out_path)]
    if highlight:
        args += ["--highlight", highlight]
    r = run(project, level, args)
    r.check_returncode()

def diagram_live(project, level, frame, highlight, out_path):
    diagram_live_names(project, level, scene_names(project, level, frame), frame, highlight, out_path)

def diagram_composite(scene_project, level, scene_names_list, missing_project, missing_actor, frame, out_path):
    """Render `scene_names_list` as they stand in `scene_project`, PLUS
    `missing_actor` reinserted from `missing_project` -- for an actor that
    doesn't exist in `scene_project`."""
    tmp = out_path.parent / "_t3d"
    tmp.mkdir(exist_ok=True)
    scene_file = tmp / f"{out_path.stem}_scene.t3d"
    missing_file = tmp / f"{out_path.stem}_missing.t3d"
    scene_file.write_text(show(scene_project, level, scene_names_list))
    missing_file.write_text(show(missing_project, level, [missing_actor]))
    args = ["actor", "diagram", "--from-t3d", str(scene_file), str(missing_file),
            "--layout", "quad", "--faces", "wire", "--brush-colors", "csg",
            "--frame", frame, "--highlight", missing_actor, "--size", "1800", "--out", str(out_path)]
    r = run(scene_project, level, args)  # project irrelevant under --from-t3d, kept for a stable env
    r.check_returncode()

def render_view(render_project, other_project, level, frame, actor, out_path):
    """Render `actor` highlighted from `render_project`'s current state, its
    scene bbox-filtered to `frame`. If `actor` doesn't exist there (deleted
    for an AFTER render, not-yet-created for a BEFORE render), reinsert it
    from `other_project` (composite) so it's still visible at its last
    known position."""
    names = scene_names(render_project, level, frame)
    if actor_exists(render_project, level, actor):
        diagram_live_names(render_project, level, names, frame, actor, out_path)
        return
    if actor_exists(other_project, level, actor):
        scene = [n for n in names if n != actor]
        diagram_composite(render_project, level, scene, other_project, actor, frame, out_path)
        return
    diagram_live_names(render_project, level, names, frame, None, out_path)
