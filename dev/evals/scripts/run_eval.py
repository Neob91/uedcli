"""Run a subagent against a task, with only the skill(s) under test in
scope, and land the result where the grading webapp picks it up
automatically. Automates the manual procedure in ../EVAL-PROCEDURE.md --
read that first, it explains WHY each step exists (why isolated HOME +
CLAUDE_CODE_OAUTH_TOKEN instead of --bare, why Docker doesn't help, the
sandbox-specific CLAUDE.md caveat) and covers the case none of this
handles: a real ANTHROPIC_API_KEY, where --bare is the cleaner mechanism
instead.

Copies the task's base trunk + the skill(s) under test into an isolated
run dir, runs `claude -p <task req>` there (isolated HOME, no ambient
project-level skills or CLAUDE.md), auto-resumes with this eval's standing
scripted reply ("Go with your recommendation.") if the agent asks a
question instead of finishing, then renders the resulting trunk and
rebuilds the page so the run shows up in the webapp -- grading itself
stays manual, by design. Model is pinned to Sonnet (CLAUDE_MODEL below),
never whatever the CLI defaults to.

`skill_dir` is either ONE skill (a directory with its own SKILL.md) or a
directory OF skills (e.g. a plugin's skills/ dir, one SKILL.md per
immediate subdirectory) -- every skill found gets installed, so a
"combined toolkit" run is just pointing at the parent directory. Isolating
to exactly one skill (the original, still-default use) is just pointing
at that skill's own directory instead.

Usage: run_eval.py <task_id> <skill_dir> [--run-id ID] [--label TEXT]

Needs an OAuth token: CLAUDE_CODE_OAUTH_TOKEN if set in the environment, else
pulled straight from ~/.claude/.credentials.json's own claudeAiOauth.accessToken
-- so it just works on a host that's already logged into Claude Code, no
separate `claude setup-token` step needed there. See EVAL-PROCEDURE.md step 1
for the setup-token path on a host that ISN'T already logged in.
"""
import argparse, datetime, html, json, os, pathlib, shutil, stat, subprocess, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from build_gold import BASE_TRUNKS_DIR, base_trunk_for, PY as VENV_PY
from extract_execution import extract_execution
from render_execution import render_execution
SCRIPTS_DIR = pathlib.Path(__file__).parent
SCRIPTED_REPLY = "Go with your recommendation."
CLAUDE_MODEL = "sonnet"  # pin the model under test -- never let it drift with whatever's default
CLAUDE_TIMEOUT_S = 3600
QUESTION_MARKERS = ("?", "your call", "which would you like", "should i", "shall i",
                    "let me know", "waiting on", "need your", "not sure whether")
# Appended to the task req, not part of it -- keeps the agent's own responses (the one where it
# flags something, and its final summary) short enough to actually read while grading. build_page.py
# imports this same constant to show the FULL prompt the agent received, so the two never drift.
RESPONSE_LENGTH_NOTE = ("\n\nKeep each of your own responses -- including if you ask a question, "
                         "and your final summary -- to at most 40 words.")

def full_prompt(task: dict) -> str:
    """The exact prompt text `claude -p` gets: the task's own req (HTML-unescaped -- it's stored
    entity-encoded for the page), plus RESPONSE_LENGTH_NOTE. NOT part of the task's own req -- it's
    a run mechanic, not something a task author writes -- but the human grading an execution should
    still be able to see exactly what the agent was actually given, hence build_page.py imports this
    same function rather than recomputing it."""
    return html.unescape(task["req"]) + RESPONSE_LENGTH_NOTE

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
    r = subprocess.run(["claude", *extra_args, "--model", CLAUDE_MODEL, "--output-format", "json"],
                        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_S)
    if not r.stdout.strip():
        raise RuntimeError(f"claude produced no output (rc={r.returncode}): {r.stderr[-2000:]}")
    return json.loads(r.stdout)

def _oauth_token() -> str:
    """CLAUDE_CODE_OAUTH_TOKEN if set, else pulled straight from this host's OWN
    already-authenticated Claude Code login (~/.claude/.credentials.json's
    claudeAiOauth.accessToken) -- owner-directed: skip the separate `claude
    setup-token` dance on a host that's already logged in."""
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if token:
        return token
    creds_path = pathlib.Path.home() / ".claude" / ".credentials.json"
    if not creds_path.exists():
        sys.exit("CLAUDE_CODE_OAUTH_TOKEN not set and no ~/.claude/.credentials.json found -- "
                  "see EVAL-PROCEDURE.md step 1 (claude setup-token)")
    try:
        token = json.loads(creds_path.read_text())["claudeAiOauth"]["accessToken"]
    except (json.JSONDecodeError, KeyError) as e:
        sys.exit(f"{creds_path} doesn't have the expected claudeAiOauth.accessToken shape: {e}")
    if not token:
        sys.exit(f"{creds_path}'s claudeAiOauth.accessToken is empty")
    return token

def _resolve_skills(skill_dir: pathlib.Path) -> list[pathlib.Path]:
    """`skill_dir` is either ONE skill (has its own SKILL.md) or a directory OF skills (each
    immediate subdirectory has one -- e.g. a plugin's skills/ dir). Returns every skill directory
    to install; exits clearly if neither shape matches."""
    if (skill_dir / "SKILL.md").exists():
        return [skill_dir]
    found = sorted(d for d in skill_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
    if not found:
        sys.exit(f"{skill_dir} has no SKILL.md, and none of its subdirectories do either")
    return found

def _needs_followup(result: dict) -> bool:
    """Best-effort: did the agent stop by asking something / flagging a
    decision instead of actually finishing? Not perfect -- errs toward
    resuming, since a spurious resume gets the same canned reply either
    way, while a missed one leaves an unfinished trunk ungraded."""
    if result.get("is_error"):
        return True
    text = (result.get("result") or "").lower()
    return any(m in text for m in QUESTION_MARKERS)

def run_eval(task_id: str, skill_dir: pathlib.Path, run_id: str) -> tuple[pathlib.Path, list[dict]]:
    """Returns (trunk_dir, llm_turns) -- llm_turns is what the agent actually said, in order: a
    `question` turn if it flagged something and got the scripted reply, then always a `final` turn
    (the only turn, if it never flagged anything). Persisted by extract_execution.py so a grader can
    see what the agent said, not just what it did."""
    if task_id not in TASKS:
        sys.exit(f"unknown task_id {task_id!r} -- known: {', '.join(sorted(TASKS))}")
    task = TASKS[task_id]
    token = _oauth_token()
    skills = _resolve_skills(skill_dir)

    run_root = BASE_TRUNKS_DIR / "eval_runs" / f"{task_id}_{run_id}"
    if run_root.exists():
        sys.exit(f"{run_root} already exists -- pick a different --run-id")
    trunk_dir = run_root / "trunk"
    shutil.copytree(base_trunk_for(task), trunk_dir)
    for s in skills:
        shutil.copytree(s, trunk_dir / ".claude" / "skills" / s.name)
    skill_names = ", ".join(s.name for s in skills)

    home_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"geomeval_home_{task_id}_{run_id}_"))
    llm_turns = []
    try:
        _make_uedcli_shim(home_dir / "bin")
        req = full_prompt(task)
        print(f"[run_eval] launching claude in {trunk_dir} (skills={skill_names})")
        result = _run_claude(trunk_dir, home_dir, task["level"], token, ["-p", req])
        session_id = result["session_id"]
        print(f"[run_eval] session {session_id}: {result.get('result', '')[:200]!r}")

        if _needs_followup(result):
            print("[run_eval] agent flagged something -- resuming with scripted reply")
            llm_turns.append(dict(kind="question", text=result.get("result", "")))
            result = _run_claude(trunk_dir, home_dir, task["level"], token,
                                  ["-p", "--resume", session_id, SCRIPTED_REPLY])
            print(f"[run_eval] resumed: {result.get('result', '')[:200]!r}")
        llm_turns.append(dict(kind="final", text=result.get("result", "")))
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)

    print(f"[run_eval] done -- trunk at {trunk_dir}")
    return trunk_dir, llm_turns

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id")
    ap.add_argument("skill_dir", type=pathlib.Path,
                     help="a skill directory (has its own SKILL.md), or a directory of skills "
                          "(each immediate subdirectory has one, e.g. a plugin's skills/ dir) -- "
                          "every skill found is installed")
    ap.add_argument("--run-id", default=None, help="defaults to a UTC timestamp")
    ap.add_argument("--label", default=None, help="shown on the page; defaults to the skill dir's name")
    args = ap.parse_args()

    run_id = args.run_id or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = args.label or args.skill_dir.name
    trunk_dir, llm_turns = run_eval(args.task_id, args.skill_dir, run_id)

    extract_execution(args.task_id, trunk_dir, run_id, label, llm_turns=llm_turns)
    manifest = render_execution(args.task_id, run_id)
    print(f"[run_eval] rendered {len(manifest['entries'])} touched entries")

    subprocess.run([VENV_PY, str(SCRIPTS_DIR / "build_page.py")], cwd=str(SCRIPTS_DIR), check=True)
    print(f"[run_eval] page rebuilt -- \"{label}\" is up under {args.task_id} for grading")
