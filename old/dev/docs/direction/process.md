# Process — how the project is run

## What we want

Who decides what, where a decision lands, and what must happen before work is done. The operative
procedures live in `CLAUDE.md` and `../rules/`; this doc says what they are for and why they are shaped
that way.

**Four lanes, split by WHO DECIDED — never by subject.** Subject-splitting loses a category: a process
ruling is the owner's but is keyed to no code module, so a subject-keyed intent doc and a module-keyed
rationale doc both have nowhere to put it. This doc is that home.

| Lane | Holds | Owner |
|-------------------------------|--------------------------------------------------------|---
| `direction/<topic>.md` | what the **owner** decided — product intent AND process rulings | theirs; agents must ask |
| `../rationale/<topic>.md` | why the **code** is the way it is — an engineering choice an agent made | agents, freely |
| `../architecture.md` + `../unrealed/*.md` | what **IS** — current implementation, verified engine facts | agents; tracks the code |
| `../rules/` + `CLAUDE.md` | the **process rules** — the procedure an agent follows | agents, freely |

- **A doc is REVISED to say the current answer.** No supersession, no dated entries, no ledger, in any
  lane. Git holds what a doc used to say. Evidence citations and live-finding dates are kept, because
  they are facts, not history.
- **A gap between `direction/` and `../architecture.md` is expected** — it is work not yet done. Two
  docs in the *same* lane disagreeing is a bug.
- **No `dev/docs/` doc may be written without the owner's explicit yes**, except `dev/docs/board/` —
  the rule is `CLAUDE.md` "dev/docs — never edit without the owner's approval". `direction/` is the
  strictest case: it governs work that may not start for months, so a corruption there surfaces
  slowest.
- **The `Confirmed:` trailer is an audit marker, not a gate, and there is no enforcement hook.** A
  pre-commit hook cannot see the message it would check (it runs before the message exists), and
  `core.hooksPath` would override the system-wide no-force-push hook. Append-only once bought
  detectability — a bad edit stood out among pure appends; revise-in-place makes a bad edit look like a
  good one, and nothing mechanical replaces that.
- **Nothing load-bearing lives only in chat.** A finding, deferral, refutation, assumption, or flag for
  the owner goes on the board (`../board/`) or into the commit message, because chat scrolls away. The
  board is a set of stage queues named for the next action an item needs.
- **A feature is built in its own git worktree** and squash-merged back into the branch the main
  checkout is on — **one commit per feature**. Several agent sessions work this repo at once, and `git
  checkout` in a shared checkout swaps files under all of them; a worktree cannot. The agent does not
  ask which branch and never switches the main checkout's branch. Procedure: `CLAUDE.md` "Feature
  worktrees". An exception is the owner's call, made live — never a standing rule recorded here.
- **Exactly ONE canonical rule file**, with no second rule file above it delegating to it. A session
  that loads two rule files loads a seam that invites the two to disagree.
- **uedcli and its pytest suite run HOST-NATIVE; only the Rust build is containerized.** Python 3 is on
  most hosts, Rust is not — so the CLI and pytest run on the host in a `python3.12` venv (native asset
  access, and the CLI reaches the docker daemon directly to drive the editor/game RUNTIME containers),
  and the one thing that needs a container is building `uedcli_native`: `ensure_native_ext` builds the
  abi3 wheel in a Rust+`libpython` image and `pip`-installs it into the venv, where the `cargo test`
  goldens also run. The toolchain stays out-of-box (host needs only `python3.12` + Docker), and uedcli
  never branches on "am I in a container?". Mechanics: `../dev-runtime.md`, `../rules/tests.md`.
  *(Owner ruling 2026-08-06.)*
- **A permanently-red test is repaired or skipped, never left red** — a suite that is always red trains
  everyone to ignore red.

## Rejected

- **An append-only decisions ledger.** It reached ~9,000 lines and 227 entries with supersession chains
  to follow, and the hand-reconciled "compiled target" derived from it silently drifted. A topic doc
  revised in place states the current answer once, and git keeps the history.
- **Folding "what we want" into "what is"** (one `architecture.md`) — a genericity *goal* once landed
  in `architecture.md` as if it were current behavior, the exact confusion the split fixes.
- **Auto-compiling one doc from another** — a generated doc is a second thing to keep true, and it is
  the thing that drifted.
- **Splitting the two decision trees by SUBJECT rather than by who decided** — process rulings fall
  through the crack.
- **Enforcing the confirmation rule with a git hook** — demonstrated unworkable, and the
  `core.hooksPath` override would risk the no-force-push rule for a marker.
- **A shared rule file sitting above the per-tool ones** — the obvious de-duplication, rejected because
  the delegation seam had already produced a stale quotation. Known cost, kept visible: work done
  outside a tool's own directory loads no rule file at all.
- **Confirming the merge target before starting feature work** — replaced by "the base is the branch
  the main checkout is on". The owner did not want to be asked.
- **Recording a standing worktree exception** — an exception is declared live, per case.
- **Worktrees as sibling directories outside the repo** — `.claude/worktrees/` matches the harness's
  convention and is gitignored.
- **Letting the harness's worktree tool keep its default base** — it branches from
  `origin/<default-branch>`, contradicting "branch off the branch we are on". The repo commits
  `.claude/settings.json` with `worktree.baseRef: "head"`.
- **Running uedcli (and pytest) inside a dev container** — the CLI in a container then can't reach the
  docker daemon to drive the RUNTIME containers wherever the daemon isn't a plain local socket, and
  external asset roots would have to be bind-mounted. Only the Rust build is containerized.
- **Repairing the spike-harness-dependent tests rather than skipping them** — the repair meant putting
  a spike harness directory on the test `sys.path`.

## Refs

`CLAUDE.md` "Direction docs" · "Feature worktrees" · [`../rules/README.md`](../rules/README.md) ·
[`../board/README.md`](../board/README.md) · [`../dev-runtime.md`](../dev-runtime.md) ·
[`../README.md`](../README.md) "Which doc is for what"
