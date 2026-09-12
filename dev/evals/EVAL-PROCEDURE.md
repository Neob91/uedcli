# Running a subagent against a task, then grading it

This is the missing half of the harness: `extract_execution.py`/`render_execution.py`/the grading
webapp (see `README.md`) grade a trunk someone already produced. This doc covers how to actually
PRODUCE one — run a subagent against a task with only the skill under test in scope — and the
isolation rationale behind it.

## Run one

```
python scripts/run_eval.py <task_id> <skill_dir>
```

On a host already logged into Claude Code, that's the whole command — no token setup needed;
`run_eval.py` pulls one straight from `~/.claude/.credentials.json`'s own `claudeAiOauth.accessToken`
(the same credential your interactive `claude` session already uses). Set `CLAUDE_CODE_OAUTH_TOKEN`
explicitly instead when running from a host that ISN'T already logged in (step 1 below covers that).

`scripts/run_eval.py` stages an isolated run directory (the task's base trunk + the skill(s) under
test), runs `claude -p <task req>` against it INSIDE a throwaway Docker container (`scripts/../docker/`,
i.e. `dev/evals/docker/`) — no ambient project-level skills, no this checkout's own `CLAUDE.md`, and
no leak of this host's `/etc/claude-code/CLAUDE.md` (see below), auto-resumes with this eval's
standing scripted reply ("Go with your recommendation.") if the agent asks a question instead of
finishing, then renders the resulting trunk and rebuilds the page so the run shows up for grading.
Model is pinned to Sonnet — never whatever the CLI defaults to. Grading itself stays manual, by
design.

`skill_dir` can point at ONE skill (isolated — only that skill is in scope, for clean attribution:
a bad run means that skill needs work) or at a directory OF skills, e.g. a plugin's `skills/` dir
(combined — every skill in it loads together, closer to how a real designer works, but a failure
doesn't tell you which skill, or the combination itself, was at fault).

If you have a real `ANTHROPIC_API_KEY` instead, `run_eval.py` doesn't use it — `--bare` is the
cleaner mechanism in that case (see below); run the manual procedure with `--bare` swapped in for
step 2, or extend `run_eval.py` to support it.

## What "isolated" means here, and what it doesn't

The goal: the agent sees the trunk, the ONE skill being evaluated, and a bare-bones Claude Code
setup — not this checkout's own `CLAUDE.md`, not some other project's skills, not leftover context
from an unrelated session, and not this sandbox's own `/etc/claude-code/CLAUDE.md` org policy file
(below). Bundled Claude Code skills (`dataviz`, `code-review`, `run`, etc.) are NOT excluded — they
ship inside the `@anthropic-ai/claude-code` package itself, and the owner has confirmed that's fine;
the eval only cares about isolating *project-specific* skills, not the tool's own defaults.

**`--bare` is the CLI's documented mechanism for stricter isolation (also drops CLAUDE.md,
plugins, MCP servers, and the bundled skills) but it flatly refuses OAuth-based auth** — confirmed
by testing, not assumed: `claude --bare -p ...` fails instantly with `Not logged in`, with
`CLAUDE_CODE_OAUTH_TOKEN` set, in and out of a fresh Docker container, while the exact same
invocation without `--bare` succeeds. Its own `--help` text explains why: *"Anthropic auth is
strictly ANTHROPIC_API_KEY or apiKeyHelper via --settings (OAuth and keychain are never read)."*
If you have a real `ANTHROPIC_API_KEY` (not an OAuth token), `--bare` is the cleaner mechanism and
none of the rest of this section applies — swap step 2 below for `claude --bare -p`. Without one,
isolated `HOME` + `CLAUDE_CODE_OAUTH_TOKEN` is what actually works — but see the next point for why
that alone isn't the whole story on THIS sandbox.

**Why the subject `claude -p` runs inside Docker, not directly on the bare host.** This particular
sandbox injects an org policy file at `/etc/claude-code/CLAUDE.md` (a fixed system path, unrelated
to `HOME` or cwd) into every process it runs — including an isolated-`HOME` `claude -p`, which still
saw it (confirmed by testing: the isolated-`HOME`-only version of this harness leaked it). Nothing
about `HOME` or cwd hides a fixed system path. A plain container built from a public base image
(confirmed directly: a bare `alpine` container) never has it — it's injected by whatever launches
THIS sandbox's own top-level process specifically, not baked into any base image, so a container
`docker run` starts fresh is unaffected. `dev/evals/docker/` is that container: `Dockerfile` bakes
in Node + `@anthropic-ai/claude-code` + Pillow (uedcli's only runtime dependency); `entrypoint.sh`
installs uedcli itself fresh from a bind-mounted source tree on every container start (cheap — pure
Python, no compiled extension needed for the brush/actor verbs these evals exercise), so a container
never runs a stale copy of the checkout. Verified end-to-end, not assumed: real OAuth auth works
inside the container, `/etc/claude-code/CLAUDE.md` is genuinely absent, a real project skill loads
and is correctly named back by the agent, `uedcli` commands run correctly against a real trunk, and
`--resume` session continuity survives across two SEPARATE `docker run` invocations that share the
same bind-mounted isolated `HOME` (needed since a session's state lives under `~/.claude`, not
in-process).

An earlier attempt at this DID try Docker and dropped it — for two reasons that turned out not to
apply here: a fresh `npm install -g @anthropic-ai/claude-code` in an empty container still ships the
same bundled skills (true, but moot — bundled-skill exclusion was never actually required, see
above), and a project-level skill "mysteriously" failed to load only inside that container (root
cause never chased down). The second concern is the one worth being honest about: this design has
NOT reproduced that failure (the real end-to-end test above loaded a project skill correctly), but
the original failure's root cause was never identified either — if a project skill ever silently
fails to load only inside `dev/evals/docker/`'s container, that's the first thing to suspect.

**Docker introduced its own new problem: the agent can't run anything unattended without
`--dangerously-skip-permissions`.** The bare host's isolated-`HOME` `claude -p` auto-approves every
Bash call with zero permission prompts (headless `-p` mode's own normal behavior — every eval run
before this Docker change already ran under it). The identical invocation inside ANY container
instead asks for an approval nothing here can grant and stalls forever — tested as both root and a
non-root UID, and across two different `claude-code` versions, ruling both out as the cause; only
`--container` (any container, any config) vs. `bare host` correlates. Most likely: Claude Code's own
internal Bash-tool sandboxing fails to establish itself one level deeper inside a nested container
and falls back to requiring a human. `run_eval.py` passes `--dangerously-skip-permissions` — the
owner explicitly chose this over a scoped `--allowedTools "Bash(uedcli:*)"` allowlist, a broader
`Bash(*)` allowlist, or restricting the container's network first, accepting the flag's own `--help`
caveat ("recommended only for sandboxes with no internet access" — this container needs internet
access for the API itself) specifically to match what every eval run already did on the bare host.

**A bind-mount source must be visible to whatever actually runs `docker run`, which this sandbox's
own `/tmp` is NOT** — confirmed directly: mounting a path under `/tmp` (this session's private
scratch space) produced an EMPTY directory inside the container with no error, while the identical
setup under this checkout (e.g. `dev/evals/_scratch/`) mounted correctly. `run_eval.py`'s isolated
`HOME` lives under `run_root` (already inside the checkout) for exactly this reason — anything else
that bind-mounts into this container needs to do the same, never `tempfile.mkdtemp()`'s default.

## The manual procedure `run_eval.py` automates

Read this if you're debugging `run_eval.py`, replicating a step by hand, or don't have it available
for some reason — otherwise just run it, above.

**1. Get an auth token.** Either a real `ANTHROPIC_API_KEY` (then use `--bare`, see above), or a
Claude Code OAuth token: `claude setup-token` (run it in a real interactive terminal — it needs a
browser/TTY, it will hang under a headless driver) prints a long-lived token. Export it as
`CLAUDE_CODE_OAUTH_TOKEN`; never put it in a committed file or a script argument list.

**2. Stage the run directory — under the checkout, NOT the system tempdir.** `mktemp -d` defaults
to `/tmp`, which is not guaranteed visible to whatever actually runs `docker run` on this sandbox
(confirmed directly — see above). Use a directory under `dev/evals/_scratch/` instead:
```
run_dir="dev/evals/_scratch/manual_run_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$run_dir/home"
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import shutil
from build_gold import base_trunk_for
from registry import TASKS
shutil.copytree(base_trunk_for(TASKS['<task_id>']), '$run_dir/trunk')
"
mkdir -p "$run_dir/trunk/.claude/skills/<skill-name>"
cp <path-to-skill>/SKILL.md "$run_dir/trunk/.claude/skills/<skill-name>/"
```
`base_trunk_for(task)` imports the task's own `dx_map` fresh into `BASE_TRUNKS_DIR` (cached after
the first import) — there's no fixed path to `cp` from. `<task.level>` comes from the task's own
`tasks/<task_id>/task.json`; the actual prompt text for step 3 below is `run_eval.full_prompt(task)`
(`req`, HTML-unescaped since it's stored entity-encoded for the webapp, plus a fixed note keeping
the agent's own responses short enough to read while grading) — not `task['req']` alone.

**3. Build the image (once) and run the agent inside it.** No PATH shim needed — `uedcli` is a
real console-script entry point once `dev/evals/docker/entrypoint.sh` installs it from the
bind-mounted source, exactly like a normal `pip install`. `--user "$(id -u):$(id -g)"` keeps the
container off root (least-privilege — it is NOT what makes the next flag necessary, see below).
`--dangerously-skip-permissions` is required for the agent to run `uedcli` (or any Bash command) at
all here — confirmed by testing: the exact same isolated-HOME + `-p` + OAuth-token invocation
auto-approves every Bash call on the bare host with zero prompts (headless `-p` mode's own normal
behavior), but the identical invocation inside ANY container instead asks for an approval nothing
here can grant and stalls forever. Owner-approved despite the flag's own `--help` caveat
("recommended only for sandboxes with no internet access" — this container needs internet access
for the API itself) specifically to match the bare host's own equally-unrestricted default:
```
docker build -t geomeval-claude:latest dev/evals/docker
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/uedcli":/uedcli-src/uedcli:ro \
  -v "$PWD/pyproject.toml":/uedcli-src/pyproject.toml:ro \
  -v "$PWD/$run_dir/trunk":/work \
  -v "$PWD/$run_dir/home":/root \
  -w /work -e HOME=/root -e UEDCLI_LEVEL=<task.level> \
  -e CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
  geomeval-claude:latest \
  claude -p "<full_prompt(task)>" --dangerously-skip-permissions \
  --model sonnet --output-format json > "$run_dir/result.json"
session_id=$(python3 -c "import json,sys;print(json.load(open('$run_dir/result.json'))['session_id'])")
```

**4. If the agent asks a question / flags something instead of just finishing:** resume with the
scripted reply this eval always uses — flagging mid-work is fine, stopping isn't, and the reply is
identical regardless of what was flagged. Reuse the SAME `-v .../home:/root` mount as step 3 —
that's where the session state from the first call lives:
```
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/uedcli":/uedcli-src/uedcli:ro \
  -v "$PWD/pyproject.toml":/uedcli-src/pyproject.toml:ro \
  -v "$PWD/$run_dir/trunk":/work \
  -v "$PWD/$run_dir/home":/root \
  -w /work -e HOME=/root -e UEDCLI_LEVEL=<task.level> \
  -e CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
  geomeval-claude:latest \
  claude -p --resume "$session_id" --dangerously-skip-permissions \
  --model sonnet "Go with your recommendation."
```
Grade the FINAL trunk state either way — a flag mid-work is not itself a failure, an unresolved
one (agent stops without finishing) is.

**5. Grade it.** `$run_dir/trunk` is now the subject trunk, exactly like any other:
```
cd scripts
python extract_execution.py <task_id> "$run_dir/trunk" --label "<skill-name>, <date>"
python render_execution.py <task_id> <run_id>
python build_page.py
```
Then open the page and score it. The `extract_execution.py` CLI doesn't have a flag for what the
agent actually said (`run_eval.py` passes that as `llm_turns=` when calling the function directly)
-- a manual run's execution card just won't show any of it.

## Open, not yet done

- `run_eval.py` only supports the OAuth-token isolated-`HOME` path above, not `--bare`/a real
  `ANTHROPIC_API_KEY` — extend it if that's what you have.
- `--resume` preserving `--bare`'s isolation (for whoever eventually has a real API key) is
  unverified — the auth failure blocked testing it at all.
- Base trunks (`BASE_TRUNKS_DIR`) live in job-scratch, not committed (DX content, not ours to
  commit) and not durable across sessions by design for now — re-extract as needed.
