"""Run a subagent against a task, with only the skill(s) under test in
scope, and land the result where the grading webapp picks it up
automatically. Automates the manual procedure in ../EVAL-PROCEDURE.md --
read that first, it explains WHY each step exists (why the subject `claude
-p` runs in Docker, why isolated HOME alone doesn't hide this sandbox's own
/etc/claude-code/CLAUDE.md) and covers the case none of this handles: a real
ANTHROPIC_API_KEY, where `--bare` is the cleaner mechanism instead.

Copies the task's base trunk + the skill(s) under test into an isolated run
dir, runs `claude -p <task req>` against it INSIDE a throwaway Docker
container (../docker/) -- no ambient project-level skills, no this
checkout's own CLAUDE.md, and no leak of this host's /etc/claude-code/
CLAUDE.md (a sandbox-specific org policy file at a fixed system path that
isolated HOME on the bare host can't hide, since it's unrelated to HOME or
cwd -- confirmed leaking in an earlier isolated-HOME-only version of this
script). Auto-resumes with this eval's standing scripted reply ("Go with
your recommendation.") if the agent asks a question instead of finishing,
then renders the resulting trunk and rebuilds the page so the run shows up
in the webapp -- grading itself stays manual, by design. Model is pinned to
Sonnet (CLAUDE_MODEL below), never whatever the CLI defaults to.

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

All bind-mount sources MUST live under this checkout (e.g. under
dev/evals/_scratch/, never the system tempdir) -- confirmed on the sandbox
this was built on: its own /tmp is private to the coding session and isn't
visible to whatever actually runs `docker run`, while paths under the
checkout are. `run_eval()` follows this itself (BASE_TRUNKS_DIR is already
under the checkout); anything extending it should too.
"""
import argparse, datetime, html, json, os, pathlib, shutil, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS
from build_gold import BASE_TRUNKS_DIR, DX_GAME_DIR, base_trunk_for, PY as VENV_PY
from extract_execution import extract_execution
from render_execution import render_execution
SCRIPTS_DIR = pathlib.Path(__file__).parent
REPO_ROOT = SCRIPTS_DIR.parents[2]
DOCKER_DIR = SCRIPTS_DIR.parent / "docker"
DOCKER_IMAGE = "geomeval-claude:latest"
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
# uedcli's own source is reachable from inside the container (bind-mounted read-only for
# entrypoint.sh's install step, at /uedcli-src) -- this eval tests whether a skill correctly
# guides real-world uedcli USAGE, not whether the agent can read the implementation and shortcut
# around it. A run mechanic, not something a task author writes -- same reasoning as
# RESPONSE_LENGTH_NOTE above.
NO_SOURCE_READING_NOTE = ("\n\nTreat uedcli as a black-box CLI: use --help and its own documented "
                          "output only. Never read uedcli's own source code (e.g. anything under "
                          "/uedcli-src), even if you can find it.")

def full_prompt(task: dict) -> str:
    """The exact prompt text `claude -p` gets: the task's own req (HTML-unescaped -- it's stored
    entity-encoded for the page), plus RESPONSE_LENGTH_NOTE and NO_SOURCE_READING_NOTE. NOT part of
    the task's own req -- these are run mechanics, not something a task author writes -- but the
    human grading an execution should still be able to see exactly what the agent was actually
    given, hence build_page.py imports this same function rather than recomputing it."""
    return html.unescape(task["req"]) + RESPONSE_LENGTH_NOTE + NO_SOURCE_READING_NOTE

def _ensure_native_wheel() -> pathlib.Path:
    """Builds (or reuses, via its own freshness hash) a uedcli_native wheel through this repo's
    OWN dev tooling (bin/_venv.sh's ensure_native_ext -- the same mechanism bin/uedcli and the
    frozen render worktree already use), so the eval image can bake it in: `actor add`/`brush
    build`/`actor duplicate` need it to parse a real .u package's class schema (confirmed by
    testing -- schema loading calls straight into uedcli_native.parse_package_raw). Baked into the
    IMAGE at build time (rare: first run, or after deleting the image), not bind-mounted fresh like
    uedcli's own Python source -- a native build is ~30s+, unacceptable per-container-run overhead,
    and .u package PARSING is stable, foundational code, not the actively-changing BSP/lighting
    build path -- same accepted tradeoff as RENDER_WT above."""
    subprocess.run(["bash", "-c", "source bin/_venv.sh && ensure_native_ext"],
                   cwd=str(REPO_ROOT), check=True)
    wheels = sorted((REPO_ROOT / "uedcli-native" / "target" / "wheels").glob("uedcli_native-*.whl"))
    if not wheels:
        sys.exit("uedcli-native build produced no wheel -- see the ensure_native_ext output above")
    return wheels[-1]

def _ensure_docker_image():
    """Builds ../docker/'s image if it isn't already present. uedcli's own PYTHON source is NOT
    baked in (installed fresh from a bind-mounted source tree at container start, see
    docker/entrypoint.sh) so a stale image still runs today's uedcli -- only the Dockerfile itself
    (Node, claude-code, Pillow, the uedcli_native wheel) needs a rebuild to pick up, and that
    rarely changes. The wheel is copied into the build context transiently (never committed --
    dev/evals/docker/*.whl is gitignored) since `docker build`'s context can't reach outside it."""
    check = subprocess.run(["docker", "image", "inspect", DOCKER_IMAGE], capture_output=True)
    if check.returncode == 0:
        return
    print(f"[run_eval] building {DOCKER_IMAGE} (first run, or image was removed)...")
    wheel = _ensure_native_wheel()
    staged_wheel = DOCKER_DIR / wheel.name
    shutil.copy(wheel, staged_wheel)
    try:
        subprocess.run(["docker", "build", "-t", DOCKER_IMAGE, str(DOCKER_DIR)], check=True)
    finally:
        staged_wheel.unlink(missing_ok=True)

def _run_claude(cwd: pathlib.Path, home: pathlib.Path, level: str, token: str, extra_args: list[str]) -> dict:
    """Runs `claude` inside a throwaway `--rm` container, not on the bare host -- see the module
    docstring for why. `cwd` (the subject trunk) and `home` (this run's isolated HOME, shared
    across the initial call and any --resume so session state survives between them) are
    bind-mounted; uedcli's own source is bind-mounted read-only and installed fresh inside the
    container by docker/entrypoint.sh, never baked into the image.

    `--user <host-uid>:<host-gid>` (not root) so the bind-mounted `cwd`/`home` (owned by whoever
    runs this script) stay writable -- general least-privilege, not itself the fix for the point
    below (confirmed by testing: switching only the UID, container vs. container, changed nothing).

    `--dangerously-skip-permissions` is required for the agent to run `uedcli` (or any Bash command)
    unattended at all -- confirmed by testing, not assumed: the identical isolated-HOME + `-p` +
    OAuth-token invocation on the bare host (no Docker) auto-approves every Bash call with zero
    permission prompts (this is headless `-p` mode's own normal behavior), but the SAME invocation
    inside ANY container (root or non-root UID, any claude-code version tried) instead asks for an
    approval it has no way to grant and stalls -- most likely Claude Code's own internal Bash-tool
    sandboxing failing to establish itself one level deeper inside a nested container, and falling
    back to requiring a human. Owner-approved (2026-09-12) despite the flag's own `--help` caveat
    ("recommended only for sandboxes with no internet access" -- this container has internet access,
    needed for the API itself) specifically to match the bare host's own equally-unrestricted default,
    which every eval run before this one already ran under.

    The token is passed via `-e CLAUDE_CODE_OAUTH_TOKEN` (no `=value`) -- Docker's env-passthrough
    form, which reads the value from THIS process's own environment rather than `docker run`'s own
    argv. `/proc/<pid>/cmdline` (what `ps aux` reads) is world-readable by default; putting the
    token there would leak it to any local user on a shared host for as long as the process runs.
    `/proc/<pid>/environ` is not.

    The real Deus Ex asset tree (dev/games/deusex/{System,Textures,Sounds,Music,Maps}) is
    bind-mounted read-only too, with entrypoint.sh writing a matching ~/.uedcli/config.toml inside
    the container -- without this, `actor add`/`brush build`/`actor duplicate` (anything needing a
    class schema from a real .u package) fail outright, confirmed on a real eval run: the agent
    correctly diagnosed the missing game files as a hard blocker and couldn't complete a task that
    needed to create a new brush."""
    if not DX_GAME_DIR.exists():
        sys.exit(f"{DX_GAME_DIR} not found -- dev/games/deusex isn't set up "
                  f"(see dev/scripts/install-deusex-assets.sh)")
    cmd = [
        "docker", "run", "--rm",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-v", f"{REPO_ROOT / 'uedcli'}:/uedcli-src/uedcli:ro",
        "-v", f"{REPO_ROOT / 'pyproject.toml'}:/uedcli-src/pyproject.toml:ro",
        "-v", f"{cwd}:/work",
        "-v", f"{home}:/root",
        "-v", f"{DX_GAME_DIR}:/dx-assets:ro",
        "-w", "/work",
        "-e", "HOME=/root",
        "-e", f"UEDCLI_LEVEL={level}",
        "-e", "CLAUDE_CODE_OAUTH_TOKEN",
        DOCKER_IMAGE,
        "claude", *extra_args, "--dangerously-skip-permissions",
        "--model", CLAUDE_MODEL, "--output-format", "json",
    ]
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": token}
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT_S)
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

    # Under run_root (already inside the checkout, not the system tempdir) -- a bind-mount
    # source has to be visible to whatever actually runs `docker run`, which a bare
    # tempfile.mkdtemp() (system /tmp) is NOT guaranteed to be; confirmed on the sandbox this
    # was built on (see module docstring).
    home_dir = run_root / "home"
    home_dir.mkdir(parents=True)
    _ensure_docker_image()
    llm_turns = []
    try:
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
