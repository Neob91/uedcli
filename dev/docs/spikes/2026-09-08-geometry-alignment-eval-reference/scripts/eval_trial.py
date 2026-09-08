"""Grade a trial (any trunk -- typically a subagent's output) against a
task's oracle, AND auto-render the same diagrams + photo tour the reference
uses, pointed at the trial's own trunk -- so a trial's actual outcome is
directly, visually comparable to "what correct looks like" on the page, not
just a pass/fail number.

Usage: eval_trial.py <task_id> <subject_trunk> [--run-id ID] [--label TEXT]

Writes runs/<task_id>/<run_id>/:
  result.json   -- run metadata + check_trunk's full per-entry verdict list
  img/<scen>.png, img/pan_<i>.png  -- rendered from the SUBJECT trunk

Never grades by re-running the subject's commands -- only ever reads its
FINAL state, the same way check_trunk.py always has. Doesn't care how the
trial got there.
"""
import argparse, datetime, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from check_trunk import check_trunk
from render_from_gold import render_scenario
from render_photos import render_photos
from build_gold import BASE_TRUNKS_DIR

ROOT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/docs/spikes/2026-09-08-geometry-alignment-eval-reference")
RUNS = ROOT / "runs"
ORACLE = ROOT / "oracle"

def eval_trial(task_id: str, subject: pathlib.Path, run_id: str, label: str | None = None) -> dict:
    task = TASKS[task_id]
    baseline = BASE_TRUNKS_DIR / task["base_trunk"]
    out_dir = RUNS / task_id / run_id
    img_dir = out_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    results = check_trunk(ORACLE / f"{task_id}.json", baseline, subject)
    n_bad = sum(1 for r in results if r["verdict"] != "correct")

    for scen_id, scen in task["scenarios"].items():
        render_scenario(subject, task["level"], task["frame"], scen_id, scen, img_dir)
    render_photos(task, subject, img_dir)

    run = dict(
        task_id=task_id, run_id=run_id, label=label or run_id,
        subject_trunk=str(subject),
        graded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        n_total=len(results), n_correct=len(results) - n_bad, n_bad=n_bad,
        passed=(n_bad == 0),
        results=results,
    )
    (out_dir / "result.json").write_text(json.dumps(run, indent=2) + "\n")
    return run

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("task_id")
    ap.add_argument("subject_trunk")
    ap.add_argument("--run-id", default=None, help="defaults to a UTC timestamp")
    ap.add_argument("--label", default=None, help="human-readable name shown on the page")
    args = ap.parse_args()

    run_id = args.run_id or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = eval_trial(args.task_id, pathlib.Path(args.subject_trunk), run_id, args.label)
    print(f"{run['n_correct']}/{run['n_total']} correct -> runs/{args.task_id}/{run_id}/result.json")
    sys.exit(0 if run["passed"] else 1)
