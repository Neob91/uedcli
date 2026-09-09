"""Run a subagent against a task, with only the skill under test in scope,
and land the result where the grading webapp picks it up automatically.
Automates the manual procedure in ../EVAL-PROCEDURE.md -- read that first,
it explains WHY each step exists (why isolated HOME + CLAUDE_CODE_OAUTH_TOKEN
instead of --bare, why Docker doesn't help, the sandbox-specific CLAUDE.md
caveat) and covers the case none of this handles: a real ANTHROPIC_API_KEY,
where --bare is the cleaner mechanism instead.

Copies the task's base trunk + the one skill directory into an isolated run
dir, runs `claude -p <task req>` there (isolated HOME, no ambient
project-level skills or CLAUDE.md), auto-resumes with this eval's standing
scripted reply ("Go with your recommendation.") if the agent asks a
question instead of finishing, then renders the resulting trunk and
rebuilds the page so the run shows up in the webapp -- grading itself
stays manual, by design.

Usage: run_eval.py <task_id> <skill_dir> [--run-id ID] [--label TEXT]

Needs CLAUDE_CODE_OAUTH_TOKEN in the environment (see EVAL-PROCEDURE.md
step 1 -- `claude setup-token`, run in a real interactive terminal).
"""
import argparse, datetime, html, json, os, pathlib, shutil, stat, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from build_gold import BASE_TRUNKS_DIR
import render_manual

VENV_PY = "/workspace/uedcli/.venv/bin/python"
SCRIPTS_DIR = pathlib.Path(__file__).parent
SCRIPTED_REPLY = "Go with your recommendation."
CLAUDE_TIMEOUT_S = 3600
QUESTION_MARKERS = ("?", "your call", "which would you like", "should i", "shall i",
                    "let me know", "waiting on", "need your", "not sure whether")

def _make_uedcli_shim(bin_dir: pathlib.Path):
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "uedcli"
    shim.write_text(f"#!/bin/sh\nexec {VENV_PY} -m uedcli \"$@\"\n")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

def _run_claude(cwd: pathlib.Path, home: pathlib.Path, level: str, token: str, extra_args: list[str]) -> dict:
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{home / 'bin'}:{os.environ['PATH']}",
        "UEDCLI_LEVEL": level,
        "CLAUDE_CODE_OAUTH_TOKEN": token,
    }
    r = subprocess.run(["claude", *extra_args, "--output-format", "json"],
                        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_S)
    if not r.stdout.strip():
        raise RuntimeError(f"claude produced no output (rc={r.returncode}): {r.stderr[-2000:]}")
    return json.loads(r.stdout)

def _needs_followup(result: dict) -> bool:
    """Best-effort: did the agent stop by asking something / flagging a
    decision instead of actually finishing? Not perfect -- errs toward
    resuming, since a spurious resume gets the same canned reply either
    way, while a missed one leaves an unfinished trunk ungraded."""
    if result.get("is_error"):
        return True
    text = (result.get("result") or "").lower()
    return any(m in text for m in QUESTION_MARKERS)

def run_eval(task_id: str, skill_dir: pathlib.Path, run_id: str) -> pathlib.Path:
    if task_id not in TASKS:
        sys.exit(f"unknown task_id {task_id!r} -- known: {', '.join(sorted(TASKS))}")
    task = TASKS[task_id]
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        sys.exit("CLAUDE_CODE_OAUTH_TOKEN not set -- see EVAL-PROCEDURE.md step 1 (claude setup-token)")
    if not (skill_dir / "SKILL.md").exists():
        sys.exit(f"{skill_dir} has no SKILL.md")

    run_root = BASE_TRUNKS_DIR / "eval_runs" / f"{task_id}_{run_id}"
    if run_root.exists():
        sys.exit(f"{run_root} already exists -- pick a different --run-id")
    trunk_dir = run_root / "trunk"
    shutil.copytree(BASE_TRUNKS_DIR / task["base_trunk"], trunk_dir)
    skill_name = skill_dir.name
    shutil.copytree(skill_dir, trunk_dir / ".claude" / "skills" / skill_name)

    home_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"geomeval_home_{task_id}_{run_id}_"))
    try:
        _make_uedcli_shim(home_dir / "bin")
        req = html.unescape(task["req"])
        print(f"[run_eval] launching claude in {trunk_dir} (skill={skill_name})")
        result = _run_claude(trunk_dir, home_dir, task["level"], token, ["-p", req])
        session_id = result["session_id"]
        print(f"[run_eval] session {session_id}: {result.get('result', '')[:200]!r}")

        if _needs_followup(result):
            print("[run_eval] agent flagged something -- resuming with scripted reply")
            result = _run_claude(trunk_dir, home_dir, task["level"], token,
                                  ["-p", "--resume", session_id, SCRIPTED_REPLY])
            print(f"[run_eval] resumed: {result.get('result', '')[:200]!r}")
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)

    print(f"[run_eval] done -- trunk at {trunk_dir}")
    return trunk_dir

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id")
    ap.add_argument("skill_dir", type=pathlib.Path, help="directory containing the skill's SKILL.md (and any other skill files)")
    ap.add_argument("--run-id", default=None, help="defaults to a UTC timestamp")
    ap.add_argument("--label", default=None, help="shown on the page; defaults to the skill dir's name")
    args = ap.parse_args()

    run_id = args.run_id or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = args.label or args.skill_dir.name
    trunk_dir = run_eval(args.task_id, args.skill_dir, run_id)

    manifest = render_manual.render_execution(args.task_id, trunk_dir, run_id, label)
    print(f"[run_eval] rendered {len(manifest['entries'])} touched entries")

    subprocess.run([VENV_PY, str(SCRIPTS_DIR / "build_page.py")], cwd=str(SCRIPTS_DIR), check=True)
    print(f"[run_eval] page rebuilt -- \"{label}\" is up under {args.task_id} for grading")
