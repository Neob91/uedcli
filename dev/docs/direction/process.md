# Process — how the project is run

## What we want

Who decides what, where a decision lands, and what has to happen before work is
called done. The **operative procedures** live in `CLAUDE.md` and `../rules/`;
this doc says what they are for and why they are shaped that way.

**Four lanes, split by WHO DECIDED — never by subject.** Subject-splitting loses
a whole category: a process ruling is the owner's but is keyed to no code module,
so a subject-keyed intent doc and a module-keyed rationale doc both have nowhere
to put it. This doc is that home.

| Lane | Holds | Owner |
|-------------------------------|--------------------------------------------------------|---
| `direction/<topic>.md` | what the **owner** decided — product intent AND process rulings | theirs; agents must ask |
| `../rationale/<topic>.md` | why the **code** is the way it is — an engineering choice an agent made | agents, freely |
| `../architecture.md` + `../unrealed/*.md` | what **IS** — current implementation, verified engine facts | agents; tracks the code |
| `../rules/` + `CLAUDE.md` | the **process rules** — the procedure an agent follows | agents, freely |

- **A doc is REVISED to say the current answer.** No supersession, no dated
  entries, no ledger, in any lane. Git holds what a doc used to say. Evidence
  citations and live-finding dates are kept, because they are facts, not history.
- **A gap between `direction/` and `../architecture.md` is expected** — it is
  work not yet done. Two docs in the *same* lane disagreeing is a bug.
- **No `dev/docs/` doc may be written without the owner's explicit yes**, except
  `dev/docs/board/` — the rule is `CLAUDE.md` "dev/docs — never edit without the
  owner's approval". `direction/` is the strictest case: it governs work that may
  not start for months, so a corruption there surfaces slowest.
- **The `Confirmed:` trailer is an audit marker, not a gate, and there is NO
  enforcement hook.** A `pre-commit` hook provably cannot see the message it
  would have to check: it runs before the message exists and takes no arguments,
  so reading `.git/COMMIT_EDITMSG` shows the *previous* commit's message and it
  passes whenever the commit before it was confirmed — failing open while looking
  green. And `core.hooksPath` is a single value that would override the
  system-wide pre-push hook enforcing no-force-push. Be clear-eyed about the
  cost: append-only bought **detectability** — a violation preserved the prior
  text and stood out among pure appends. Revise-in-place destroys the prior text
  and makes a bad edit look exactly like a good one. **Nothing mechanical
  replaces that.**
- **Nothing load-bearing lives only in chat.** A finding left standing, a
  deferral, a refutation, an assumption, a flag for the owner — each goes on the
  board (`../board/`) or into the commit message, because chat scrolls away. The
  board is a set of stage queues named for the *next action* an item needs.
- **A feature is built in its own git worktree** and squash-merged back into the
  branch the main checkout is already on — **one commit per feature**. Several
  agent sessions work this repo at once, and `git checkout` in a shared checkout
  swaps files under all of them mid-edit; a worktree structurally cannot. The
  agent does **not** ask which branch and never switches the main checkout's
  branch. Procedure: `CLAUDE.md` "Feature worktrees". **An exception is the
  owner's call, made live in the session — never a standing rule recorded here.**
- **Exactly ONE canonical rule file**, with no second rule file above it
  delegating to it. A session that loads two rule files loads a seam, and the
  seam invites the two to disagree.
- **uedcli and its pytest suite run HOST-NATIVE; only the Rust build is
  containerized.** Python 3 is on most hosts, Rust is not — so the CLI and pytest
  run on the host in a `python3.12` venv (native asset access, and the CLI reaches
  the docker daemon directly to drive the editor/game RUNTIME containers), and the
  ONE thing that needs a container is building `uedcli_native`: `ensure_native_ext`
  builds the abi3 wheel in a Rust+`libpython` image and `pip`-installs it into the
  venv, and the `cargo test` goldens run there too. So the toolchain is
  out-of-box (host needs only `python3.12` + Docker; no Rust install, and the
  `-lpython3.12` link a bare host lacked is supplied by the image), while dev path
  handling stays prod path handling — uedcli never branches on "am I in a
  container?". Mechanics: `../dev-runtime.md`, `../rules/tests.md`. *(Owner ruling
  2026-08-06.)*
- **A permanently-red test is repaired or skipped, never left red** — a suite
  that is always red trains everyone to ignore red, which costs more than the
  coverage the red test represents.

## Rejected

- **An append-only decisions ledger.** It reached ~9,000 lines and 227 entries
  with supersession chains to follow, and the hand-reconciled "compiled target"
  doc derived from it silently drifted — nine of its newest entries postdated the
  newest one it reconciled. A topic doc revised in place states the current
  answer once, and git keeps the history.
- **Folding "what we want" into "what is"** (one `architecture.md`) — conflates
  the two, which is the exact confusion the split was created to fix: a
  genericity *goal* once landed in `architecture.md` as if it were current
  behavior.
- **Auto-compiling one doc from another.** No dev doc is generated; a generated
  doc is a second thing that has to be kept true, and it is the thing that
  drifted.
- **Splitting the two decision trees by SUBJECT rather than by who decided** —
  process rulings fall through the crack.
- **Enforcing the confirmation rule with a git hook** — demonstrated unworkable,
  and the `core.hooksPath` override would put a real safety rule at risk for a
  guard that was never more than a marker.
- **A shared rule file sitting above the per-tool ones.** It is the obvious
  de-duplication — one process, not two mirrored copies — and it was rejected
  anyway, because the delegation seam had already produced a stale quotation.
  **Known cost, kept visible rather than worked around:** work done outside a
  tool's own directory then loads no rule file at all.
- **Confirming the merge target before starting feature work** — replaced by "the
  base is the branch the main checkout is already on". The owner explicitly did
  not want to be asked.
- **Recording a standing worktree exception** for work whose commits must survive
  individually — an exception is declared live, per case, not written down as a
  rule that the next reader treats as an opt-out.
- **Worktrees as sibling directories outside the repo** — `.claude/worktrees/`
  matches the harness's own convention (one convention, not two) and is
  gitignored, so the second checkout is invisible to git, ripgrep and the test
  runners.
- **Letting the harness's worktree tool keep its default base** — it branches
  from `origin/<default-branch>`, contradicting "branch off the branch we are
  on". The repo commits `.claude/settings.json` with `worktree.baseRef: "head"`.
- **Running uedcli (and pytest) inside a dev container**, not just the Rust build.
  It removes the `python3.12`-on-host need, but the CLI in a container then can't
  reach the docker daemon to drive the editor/game RUNTIME containers wherever the
  daemon isn't a plain local socket (here a `tcp://dind` daemon a dind-managed
  container has no route to), and external asset roots would have to be bind-mounted
  in. Host-native Python keeps both free; only the Rust build — the one dependency
  hosts lack — is containerized.
- **Repairing the spike-harness-dependent tests rather than skipping them** —
  the repair meant putting a spike harness directory on the test `sys.path`.

## Refs

`CLAUDE.md` "Direction docs" · "Feature worktrees" ·
[`../rules/README.md`](../rules/README.md) ·
[`../board/README.md`](../board/README.md) ·
[`../dev-runtime.md`](../dev-runtime.md) ·
[`../README.md`](../README.md) "Which doc is for what"
