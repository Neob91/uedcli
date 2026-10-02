"""Extract one execution's diff from a subject trunk -- the ONLY step that
ever touches the subject trunk. Writes tasks/<task_id>/executions/<run_id>/{execution.json,
diff.patch, panorama/pan_N.png}. Does NOT compute the touched-actor list,
buckets, or labels -- that's render_execution.py's job, deferred so it can
run any time later from just diff.patch + the cached base trunk, without
the subject trunk (which can be an ephemeral job tmp dir) existing at all.

The diff is `git diff --no-index --no-renames` over ONLY maps/<level>/ (not
the whole project): every subject trunk run_eval.py produces also carries
.claude/skills/<skill>/ and uedcli's own .uedcli/ state dir, neither of
which is level content -- diffing the whole project would put both into
the patch, and `patch` silently turns any binary content it can't apply
into a 0-byte file with no error. Scoping to maps/<level>/ excludes both,
and also excludes maps/.locks/ (a per-project lock dir, sibling to
maps/<level>/) with no separate exclusion needed.

Usage: extract_execution.py <task_id> <subject_trunk> [--run-id ID] [--label TEXT]
"""
import argparse, datetime, json, pathlib, shutil, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from build_gold import base_trunk_for, BASE_TRUNKS_DIR
from render_photos import render_photos
from render_common import fingerprint as _fingerprint

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "tasks"

def extract_execution(task_id: str, subject: pathlib.Path, run_id: str, label: str | None = None,
                       *, llm_turns: list[dict] | None = None) -> pathlib.Path:
    """`llm_turns` (optional): what the agent actually said, from run_eval.py -- omitted entirely
    for a subject trunk that didn't come from a live agent run (a hand-built trunk, build_gold.py's
    output)."""
    if task_id not in TASKS:
        sys.exit(f"unknown task_id {task_id!r} -- known: {', '.join(sorted(TASKS))}")
    task = TASKS[task_id]
    level = task["level"]
    baseline = base_trunk_for(task)

    out_dir = TASKS_DIR / task_id / "executions" / run_id
    if out_dir.exists():
        sys.exit(f"{out_dir} already exists -- pick a different --run-id")

    scratch = pathlib.Path(tempfile.mkdtemp(prefix=f"extract_{task_id}_{run_id}_", dir=BASE_TRUNKS_DIR.parent))
    try:
        before_copy, after_copy = scratch / "before", scratch / "after"
        shutil.copytree(baseline, before_copy)
        shutil.copytree(subject, after_copy)

        r = subprocess.run(
            ["git", "diff", "--no-index", "--no-renames",
             f"before/maps/{level}", f"after/maps/{level}"],
            cwd=scratch, capture_output=True, text=True)
        # --no-index exits 1 for "differences found" (the normal case) as well as for a real
        # access error reported on stderr (e.g. a typo'd subject_trunk missing maps/<level>/
        # entirely) -- >=2 alone would silently accept the latter as "no changes"
        if r.returncode >= 2 or r.stderr.strip():
            sys.exit(f"git diff failed (rc={r.returncode}): {r.stderr}")
        patch = r.stdout
        if "\nBinary files " in patch or "\nGIT binary patch" in patch or patch.startswith("Binary files "):
            sys.exit(f"diff.patch for {task_id}/{run_id} contains binary content under maps/{level}/ -- "
                      "that shouldn't happen (everything there should be text); needs a human look, "
                      "not a silently truncated patch")

        fingerprint = _fingerprint(before_copy, level)

        # build the whole output into a staging dir first, and only move it into place once
        # everything (including the panorama render) has actually succeeded -- otherwise a
        # render_photos failure leaves a half-written out_dir occupying this run_id with no
        # execution.json, and a retry can never get past "already exists"
        staging = scratch / "out"
        staging.mkdir()
        (staging / "diff.patch").write_text(patch)
        panorama_dir = staging / "panorama"
        panorama_dir.mkdir()
        render_photos(task, subject, panorama_dir)
        execution = dict(
            task_id=task_id, run_id=run_id, label=label or run_id,
            subject_trunk=str(subject),
            rendered_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            base_fingerprint=fingerprint,
            llm_turns=llm_turns or [],
        )
        (staging / "execution.json").write_text(json.dumps(execution, indent=2) + "\n")

        out_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), str(out_dir))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    return out_dir

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id")
    # resolve to absolute: extract_execution()'s subprocess calls run with cwd=WT, so a relative
    # subject_trunk (as typed at this script's own invocation cwd) would silently resolve against
    # the wrong directory otherwise (same trap as build_gold.py's out_dir)
    ap.add_argument("subject_trunk", type=lambda s: pathlib.Path(s).resolve())
    ap.add_argument("--run-id", default=None, help="defaults to a UTC timestamp")
    ap.add_argument("--label", default=None, help="human-readable name shown on the page")
    args = ap.parse_args()

    run_id = args.run_id or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = extract_execution(args.task_id, args.subject_trunk, run_id, args.label)
    print(f"extracted {args.task_id}/{run_id} -> {out_dir}")
