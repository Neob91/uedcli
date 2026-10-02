"""Render one already-extracted execution's per-actor pictures + manifest.json,
using ONLY the cached base trunk + diff.patch + task.json -- the subject
trunk never needs to exist. Re-runnable any time (e.g. after a rendering bug
fix): only manifest.json and entries/ are replaced -- execution.json,
diff.patch, panorama/, and grade.json are never touched, so a re-render
can't destroy an existing grade.

1. Copy the cached base trunk twice: before_copy (untouched) and after_copy.
   Verify before_copy's actor content still matches execution.json's stored
   base_fingerprint before applying anything -- the base-trunk cache can be
   deleted and re-imported later (build_gold.base_trunk_for), and applying
   diff.patch onto DIFFERENT base content needs a clear error, not
   `patch`'s default fuzzy-match silently mis-applying.
2. Apply diff.patch onto after_copy with `patch -p2 --batch --forward -F0
   --no-backup-if-mismatch` (git apply was tried first and resolves paths
   against the git repo root instead of the copy's own directory when run
   from inside this project's git worktree -- patch doesn't have that
   problem). -F0 makes any context mismatch fail loudly rather than
   fuzzy-apply, matching the fingerprint check's intent.
3. Touched-actor list: actor names in before_copy vs. after_copy (created/
   deleted by set difference) + full T3D block/order_value comparison for
   the intersection (updated) -- same comparison this pipeline always used,
   just fed two local copies instead of the original baseline/subject.
   `declared` looked up against task.json's `entries` by actor name -- NOT
   `what`: the grader sees only the actor's real name and CREATED/UPDATED/
   DELETED, never the task's own prose description of what that actor is
   "supposed" to be, which would prime the grade instead of letting the
   picture speak for itself.
4. Per touched actor, BEFORE (from before_copy, AS IT ACTUALLY STOOD before
   the task -- not a preview with this one actor spliced in) and AFTER (from
   after_copy, AS IT ACTUALLY STANDS after -- not the deleted actor spliced
   back in). A created actor simply isn't highlighted in its own BEFORE
   picture (it doesn't exist yet -- there is nothing there to point at); a
   deleted actor simply isn't highlighted in its own AFTER picture, same
   reason. No synthetic reinsertion of one trunk's actor into the other's
   scene -- every picture shows a real, actually-existing state.

Usage: render_execution.py <task_id> <run_id>
"""
import argparse, json, os, pathlib, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from build_gold import base_trunk_for, BASE_TRUNKS_DIR
import render_common as rc

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"

LABELS = {"created": "CREATED", "updated": "UPDATED", "deleted": "DELETED"}

def _order_value(project: pathlib.Path, level: str, actor: str) -> str | None:
    """The actor's raw LexoRank CSG-order sidecar (maps/<level>/actors/<actor>/
    order_value) -- NOT part of its T3D block (`actor show` never emits it),
    so a pure CSG-order change is otherwise invisible to a T3D diff."""
    p = project / "maps" / level / "actors" / actor / "order_value"
    return p.read_text() if p.exists() else None

def _all_actor_names(project, level) -> set[str]:
    r = rc.run(project, level, ["actor", "find", "--json"])
    r.check_returncode()
    return set(json.loads(r.stdout))

_ACTOR_BLOCK_RE = re.compile(r"(Begin Actor Class=\S+ Name=(\S+).*?\nEnd Actor\n)", re.DOTALL)

def _split_actor_blocks(t3d_text: str) -> dict[str, str]:
    return {m.group(2): m.group(1) for m in _ACTOR_BLOCK_RE.finditer(t3d_text)}

def _diff_local_copies(before_copy, after_copy, task) -> list[dict]:
    """Every actor that differs between before_copy and after_copy -- see module
    docstring point 3. O(1) heavy subprocess calls (2 `actor find` + up to 2 bulk
    `actor show -`), not O(actors)."""
    level = task["level"]
    base_names = _all_actor_names(before_copy, level)
    sub_names = _all_actor_names(after_copy, level)
    common = sorted(base_names & sub_names)
    base_blocks = _split_actor_blocks(rc.show(before_copy, level, common))
    sub_blocks = _split_actor_blocks(rc.show(after_copy, level, common))
    assert len(base_blocks) == len(common) and len(sub_blocks) == len(common), (
        f"_ACTOR_BLOCK_RE parsed {len(base_blocks)}/{len(sub_blocks)} of {len(common)} actors -- "
        "a parse miss here silently drops actors from the diff instead of comparing them")
    declared_actors = {e["actor"].casefold() for e in task["entries"] if e.get("actor")}

    changed = []
    for name in sorted(base_names | sub_names):
        if name in base_names and name not in sub_names:
            bucket = "deleted"
        elif name in sub_names and name not in base_names:
            bucket = "created"
        elif (base_blocks.get(name) != sub_blocks.get(name)
              or _order_value(before_copy, level, name) != _order_value(after_copy, level, name)):
            bucket = "updated"
        else:
            continue
        changed.append(dict(actor=name, bucket=bucket, declared=name.casefold() in declared_actors))
    return changed

def _render_view_copy(render_copy, level, frame, actor, scratch, out_path):
    """Render `render_copy`'s ACTUAL current state, its scene bbox-filtered to `frame`, with
    `actor` highlighted if (and only if) it actually exists there. No synthetic reinsertion of
    an actor from the other trunk: a BEFORE picture must show the real state before the task
    (a created actor gets no highlight there -- it doesn't exist yet), and an AFTER picture must
    show the real state after (a deleted actor gets no highlight there -- it's genuinely gone).
    A composite ("what would it look like if this ONE actor were undone") mixes a real state
    with a hypothetical, which is exactly the ambiguity a real diff exists to avoid. Always
    renders to a temp path first and os.replace()s it into `out_path` -- uedcli's own PNG writer
    has no tmp+rename step of its own, so without this an interrupted render (the exact scenario
    --resume exists for) can leave a truncated PNG that a later --resume run would then treat as
    already-done and skip forever."""
    tmp_out = scratch / f"_pending_{out_path.name}"
    names = rc.scene_names(render_copy, level, frame)
    highlight = actor if rc.actor_exists(render_copy, level, actor) else None
    rc.diagram_live_names(render_copy, level, names, frame, highlight, tmp_out)
    os.replace(tmp_out, out_path)

def render_execution(task_id: str, run_id: str, *, resume: bool = False) -> dict:
    if task_id not in TASKS:
        sys.exit(f"unknown task_id {task_id!r} -- known: {', '.join(sorted(TASKS))}")
    task = TASKS[task_id]
    level = task["level"]
    out_dir = TASKS_DIR / task_id / "executions" / run_id
    execution_path = out_dir / "execution.json"
    if not execution_path.exists():
        sys.exit(f"{execution_path} not found -- run extract_execution.py first")
    execution = json.loads(execution_path.read_text())

    scratch = pathlib.Path(tempfile.mkdtemp(prefix=f"render_{task_id}_{run_id}_", dir=BASE_TRUNKS_DIR.parent))
    try:
        before_copy, after_copy = scratch / "before", scratch / "after"
        shutil.copytree(base_trunk_for(task), before_copy)

        actual_fp = rc.fingerprint(before_copy, level)
        if actual_fp != execution["base_fingerprint"]:
            sys.exit(f"base trunk for {task_id} has drifted since {run_id} was extracted "
                      f"(fingerprint {actual_fp[:12]}... != {execution['base_fingerprint'][:12]}...) "
                      "-- delete and re-import the base trunk cache is not enough; this execution "
                      "needs re-extracting against the CURRENT base trunk, or the base trunk cache "
                      "needs restoring to what it was")

        shutil.copytree(before_copy, after_copy)
        patch_path = out_dir / "diff.patch"
        r = subprocess.run(
            ["patch", "-p2", "--batch", "--forward", "-F0", "--no-backup-if-mismatch"],
            cwd=after_copy, input=patch_path.read_text(), capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"applying {patch_path} onto the base trunk copy failed (rc={r.returncode}): "
                      f"{r.stdout}\n{r.stderr}")

        touched = _diff_local_copies(before_copy, after_copy, task)
        touched_actors = [t["actor"] for t in touched]
        frame = rc.frame_from_actors([before_copy, after_copy], level, touched_actors, rc.FRAME_PAD)

        entries_dir = out_dir / "entries"
        manifest_path = out_dir / "manifest.json"
        if resume:
            entries_dir.mkdir(exist_ok=True)
        else:
            # drop the old manifest FIRST: if this run gets interrupted partway (the memory-
            # pressure scenario --resume exists for), a stale manifest still pointing at images
            # entries_dir no longer has is worse than no manifest at all -- build_page.py would
            # silently render broken image links instead of just not showing this run yet
            manifest_path.unlink(missing_ok=True)
            if entries_dir.exists():
                shutil.rmtree(entries_dir)
            entries_dir.mkdir()

        entries = []
        for t in touched:
            actor = t["actor"]
            before_path = entries_dir / f"{actor}_before.png"
            after_path = entries_dir / f"{actor}_after.png"
            if not (resume and before_path.exists()):
                _render_view_copy(before_copy, level, frame, actor, scratch, before_path)
            if not (resume and after_path.exists()):
                _render_view_copy(after_copy, level, frame, actor, scratch, after_path)
            entries.append(dict(actor=actor, bucket=t["bucket"], label=LABELS[t["bucket"]],
                                 declared=t["declared"],
                                 img_before=f"entries/{actor}_before.png",
                                 img_after=f"entries/{actor}_after.png"))
        if resume:
            # drop stale images for an actor no longer in the touched set (e.g. diff.patch changed)
            wanted = {p.name for t in touched for p in (entries_dir / f"{t['actor']}_before.png",
                                                          entries_dir / f"{t['actor']}_after.png")}
            for f in entries_dir.iterdir():
                if f.is_file() and f.name not in wanted:
                    f.unlink()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    manifest = dict(
        task_id=task_id, run_id=run_id, label=execution["label"],
        subject_trunk=execution["subject_trunk"], rendered_at=execution["rendered_at"],
        llm_turns=execution.get("llm_turns", []),
        entries=entries,
        panorama=[f"panorama/pan_{i}.png" for i in range(8)],
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id")
    ap.add_argument("run_id")
    ap.add_argument("--resume", action="store_true",
                     help="keep already-rendered entries/ images instead of wiping and redoing "
                          "everything -- for continuing after an interrupted run, NOT the default "
                          "(a normal re-render should pick up a rendering fix everywhere, not just "
                          "for actors whose images happen to be missing)")
    args = ap.parse_args()
    manifest = render_execution(args.task_id, args.run_id, resume=args.resume)
    print(f"rendered {len(manifest['entries'])} entries + panorama -> "
          f"tasks/{args.task_id}/executions/{args.run_id}/manifest.json")
