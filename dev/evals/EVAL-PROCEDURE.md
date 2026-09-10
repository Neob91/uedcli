# Running a subagent against a task, then grading it

This is the missing half of the harness: `render_manual.py`/the grading webapp (see `README.md`)
grade a trunk someone already produced. This doc covers how to actually PRODUCE one — run a
subagent against a task with only the skill under test in scope — and the isolation rationale
behind it.

## Run one

```
python scripts/run_eval.py <task_id> <skill_dir>
```

On a host already logged into Claude Code, that's the whole command — no token setup needed;
`run_eval.py` pulls one straight from `~/.claude/.credentials.json`'s own `claudeAiOauth.accessToken`
(the same credential your interactive `claude` session already uses). Set `CLAUDE_CODE_OAUTH_TOKEN`
explicitly instead when running from a host that ISN'T already logged in (step 1 below covers that).

`scripts/run_eval.py` stages an isolated run directory (the task's base trunk + the skill(s) under
test), runs `claude -p <task req>` there with an isolated `HOME` (no ambient project-level skills,
no this-checkout `CLAUDE.md`), auto-resumes with this eval's standing scripted reply ("Go with your
recommendation.") if the agent asks a question instead of finishing, then renders the resulting
trunk and rebuilds the page so the run shows up for grading. Model is pinned to Sonnet — never
whatever the CLI defaults to. Grading itself stays manual, by design.

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
from an unrelated session. Bundled Claude Code skills (`dataviz`, `code-review`, `run`, etc.) are
NOT excluded — they ship inside the `@anthropic-ai/claude-code` package itself, and the owner has
confirmed that's fine; the eval only cares about isolating *project-specific* skills, not the tool's
own defaults.

**`--bare` is the CLI's documented mechanism for stricter isolation (also drops CLAUDE.md,
plugins, MCP servers, and the bundled skills) but it flatly refuses OAuth-based auth** — confirmed
by testing, not assumed: `claude --bare -p ...` fails instantly with `Not logged in`, with
`CLAUDE_CODE_OAUTH_TOKEN` set, in and out of a fresh Docker container, while the exact same
invocation without `--bare` succeeds. Its own `--help` text explains why: *"Anthropic auth is
strictly ANTHROPIC_API_KEY or apiKeyHelper via --settings (OAuth and keychain are never read)."*
If you have a real `ANTHROPIC_API_KEY` (not an OAuth token), `--bare` is the cleaner mechanism and
this whole isolated-`HOME` approach becomes unnecessary — swap step 2 below for `claude --bare -p`.
Without one, isolated `HOME` + `CLAUDE_CODE_OAUTH_TOKEN` is what actually works, verified below.

**Also confirmed, not assumed:** a fresh `npm install -g @anthropic-ai/claude-code` in an empty
Docker container still has the same bundled skills — there's nothing installed on top to strip out.
Docker was tried and dropped for this reason (plus a project-level skill mysteriously failing to
load only inside that container, root cause not chased down once bundled-skill exclusion turned
out not to matter). Plain isolated `HOME` on the host was tested end-to-end instead and works:
real auth, target skill loads, no CLAUDE.md leak from an *ordinary* host.

**One sandbox-specific wrinkle, not a design flaw:** this particular host injects an org policy
file at `/etc/claude-code/CLAUDE.md` (a fixed system path, unrelated to `HOME` or cwd) that leaked
into the isolated-`HOME` test. Only `--bare` excludes it. Irrelevant on a plain host that doesn't
have such a file; worth knowing if you're running this on one that does.

## The manual procedure `run_eval.py` automates

Read this if you're debugging `run_eval.py`, replicating a step by hand, or don't have it available
for some reason — otherwise just run it, above.

**1. Get an auth token.** Either a real `ANTHROPIC_API_KEY` (then use `--bare`, see above), or a
Claude Code OAuth token: `claude setup-token` (run it in a real interactive terminal — it needs a
browser/TTY, it will hang under a headless driver) prints a long-lived token. Export it as
`CLAUDE_CODE_OAUTH_TOKEN`; never put it in a committed file or a script argument list.

**2. Stage the run directory.**
```
run_dir=$(mktemp -d)
fake_home=$(mktemp -d)
cp -r "$BASE_TRUNKS_DIR/<task.base_trunk>" "$run_dir/trunk"
mkdir -p "$run_dir/trunk/.claude/skills/<skill-name>"
cp <path-to-skill>/SKILL.md "$run_dir/trunk/.claude/skills/<skill-name>/"
```
`<task.base_trunk>` and `<task.level>` come from the task's own `scripts/specs/<task_id>.py`. So
does `req` for step 4 below — it's HTML-entity-encoded there (`&ldquo;...&rdquo;`) for the webapp,
so unescape it (`&ldquo;`/`&rdquo;` → curly quotes, `&mdash;` → em dash, etc.) before using it as
the actual prompt text.

**3. Put `uedcli` on PATH.** The trunk is already a self-contained uedcli project (its own
`uedcli.toml`), so the agent just needs the CLI reachable — a wrapper resolving to this checkout's
own venv:
```
mkdir -p "$fake_home/bin"
cat > "$fake_home/bin/uedcli" <<'SH'
#!/bin/sh
exec /workspace/uedcli/.venv/bin/python -m uedcli "$@"
SH
chmod +x "$fake_home/bin/uedcli"
```

**4. Run the agent.**
```
cd "$run_dir/trunk"
HOME="$fake_home" PATH="$fake_home/bin:$PATH" UEDCLI_LEVEL=<task.level> \
  CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
  claude -p "<task.req>" --model sonnet --output-format json > "$run_dir/result.json"
session_id=$(python3 -c "import json,sys;print(json.load(open('$run_dir/result.json'))['session_id'])")
```

**5. If the agent asks a question / flags something instead of just finishing:** resume with the
scripted reply this eval always uses — flagging mid-work is fine, stopping isn't, and the reply is
identical regardless of what was flagged:
```
HOME="$fake_home" PATH="$fake_home/bin:$PATH" UEDCLI_LEVEL=<task.level> \
  CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_CODE_OAUTH_TOKEN" \
  claude -p --resume "$session_id" --model sonnet "Go with your recommendation."
```
Grade the FINAL trunk state either way — a flag mid-work is not itself a failure, an unresolved
one (agent stops without finishing) is.

**6. Grade it.** `$run_dir/trunk` is now the subject trunk, exactly like any other:
```
cd scripts
python render_manual.py <task_id> "$run_dir/trunk" --label "<skill-name>, <date>"
python build_page.py
```
Then open the page and score it.

## Open, not yet done

- `run_eval.py` only supports the OAuth-token isolated-`HOME` path above, not `--bare`/a real
  `ANTHROPIC_API_KEY` — extend it if that's what you have.
- `--resume` preserving `--bare`'s isolation (for whoever eventually has a real API key) is
  unverified — the auth failure blocked testing it at all.
- Base trunks (`BASE_TRUNKS_DIR`) live in job-scratch, not committed (DX content, not ours to
  commit) and not durable across sessions by design for now — re-extract as needed.
