# Handoff — native BSP build parity push (2026-08-25)

Read this first on resume. Written mid-session because the host's docker daemon wedged and
couldn't be recovered from inside this session — not because the work itself is stuck.

## Goal

Close the gap between `uedcli-native`'s Rust reimplementation of UnrealEd's BSP/CSG geometry-build
engine and the real editor, at real production scale (734-brush `03_NYC_UNATCOHQ`), following the
reverse-engineered spec in bd issue `uedcli-613ec6` (design field).

## Headline state — real, verified, all in `master`

Started this session's push at **913 node disagreements** on the full UNATCO map vs. the real
editor. Now at **448 (-51%)**, via three independent, disassembly-confirmed bugs found and fixed
today (each with a passing regression test, `cargo test --release` currently 55/55):

1. `67d6516` — CSG pass-staging: `NotSolid`-non-`Semisolid` brushes were wrongly deferred to a
   post-repartition pass; only `Semisolid` should defer. Closed the pre-repartition committed tree
   to byte-identical across the whole map (was diverging from brush 106 on).
2. `ad484ae` — `bspOptGeom` T-junction weld: missing the editor's 16-vertex ring cap.
3. `5410bd7` — `FindBestSplit`'s candidate-slot scan was stepping to the next slot boundary instead
   of scanning the whole slot for the first eligible poly (silent no-op on the small castle test,
   live and damaging at UNATCO scale). This was the single biggest jump: 913→448.
4. `c6e9e08` — a smaller, independently-confirmed `bspMergeCoplanars` scan bug (an unwarranted
   "skip already-claimed candidate" check with no basis in the disassembly). Confirmed real but
   currently inert on the aggregate UNATCO metric.

Also settled along the way: the editor's own repartition input soup (`NumPolys=2514` vs native's
2504, `d681676`) is faithful — rules out soup composition as a cause. And a forensic re-walk
(`317785e`) collapsed the apparent "260+ diffuse disagreements" picture down to **17 real
divergence origins**, of which 11 are a separate small precision-drift finding and 6 trace to 8
named surfaces where `bspMergeCoplanars` groups coplanar fragments differently than the editor.

## What's in-flight, not yet merged

**Worktree:** `/workspace/uedcli/.claude/worktrees/agent-acfdb0dc301e0a2f4`, branch
`worktree-agent-acfdb0dc301e0a2f4`. Not merged, not reviewed. Contains uncommitted work
(a corrected live probe script, per its own last report) plus whatever it committed before the
infra blocker — check `git log` and `git status` in that worktree before doing anything else.

**Task:** pin down why one of the 8 `bspMergeCoplanars` divergence cases (`iLink=1144`) rejects a
merge on the real editor that native accepts. Traced to `FPoly::RemoveColinears` — but the
investigation just hit a **genuine, doubly-confirmed contradiction**, not a loose end:

- Full fresh re-disassembly of `RemoveColinears` (`Engine.dll 0x151090`) confirms exactly the two
  passes the spec already documents — **no reflex-vertex/convexity check exists in this function**.
  This refutes the working hypothesis from earlier in the session.
- The `TryToMerge` call site (`Editor.dll 0x34de2`) was also re-checked clean — no intervening
  logic between the call and the observed return value.
- Hand-simulating the disassembled algorithm on the exact real 6-vertex ring (float32, engine
  op-order) **predicts ACCEPT** — but the live capture (both this session and the one before it)
  observed **REJECT** (`rc_eax=0`).

**Next step, as flagged by the agent itself:** re-examine the *live capture technique*, not
`RemoveColinears` further — the static analysis is now clean on both sides of the call, so if the
live data still says reject, the capture is most likely catching the wrong thing (wrong call
instance, wrong breakpoint, misread register/memory) rather than `RemoveColinears` doing something
undocumented. Start there before any more disassembly of `RemoveColinears` itself.

**Known gotcha, already paid for once — don't re-pay it:** `Editor.dll` loads unrebased but the
loader rebases `Engine.dll` by roughly `-0xF00000` from its declared base. A gdb breakpoint
computed from the static file RVA (`pefile`) can silently land on the wrong code inside
`Engine.dll`. Verify the actual runtime load address (`/proc/<pid>/maps` inside the container, or
gdb's own module-info) before trusting a static-RVA breakpoint into `Engine.dll`.

## Current blocker — infrastructure, not the investigation

The host's docker (rootless) stopped being able to fork (`resource temporarily unavailable` on
every `docker run`/`exec`) after a stray, unrelated `ugrep` process ran at **1157% CPU for ~12
hours** (not started by this session). That process was found and killed (`kill -9`, confirmed
gone, host load dropped 17→9.7 within seconds) — but docker itself did not recover afterward.
There is no visible `dockerd`/`rootlesskit`/`containerd` process from inside this container to
restart or diagnose further; the daemon this environment talks to isn't reachable from here.

**Before resuming any live-editor work**, check whether `docker run --rm alpine echo ok` succeeds.
If it still doesn't, that's an environment-level issue outside what a session working inside this
container can fix — needs host-level attention.

## Rules that governed this whole effort — keep following them on resume

- **Never cite `uedcli-native`'s own code, or any bd issue, as evidence for what UnrealEd
  itself does.** Only fresh disassembly or direct live observation of the real editor counts.
  The spec (bd issue `uedcli-613ec6`, design field) states this rule at its own top and should
  keep being the durable record of confirmed UnrealEd facts.
- `cargo test --release` (currently 55 tests) must stay 100% green after any `uedcli-native` change
  — non-negotiable. Run via:
  `docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e CARGO_HOME=/io/target/.cargo -v "$(pwd)/uedcli-native":/io -w /io uedcli-rust-build:latest cargo test --release`
- No castle-scale (`Test_Castle.dx`) fixture exists anywhere in this environment — every fix this
  session was reasoned to be a provable no-op at castle scale (by construction: the relevant
  code path never triggers on 0-detail-brush content) rather than empirically re-verified there.
  If that fixture turns up somewhere, re-run the castle gate for everything landed today.
- Real, disassembly-confirmed fixes get committed directly by the implementing session; each was
  reviewed (by a separate subagent, or by the orchestrating session directly) before being
  squash-merged onto `master` from the **main checkout** (never a worktree — see
  `dev/docs/rules/worktrees.md`), following: `git pull --ff-only`, `git merge --squash <branch>`,
  inspect `git status --short` for anything unexpected staged, commit, push, verify with
  `git diff <branch> HEAD -- <touched paths>` prints nothing, then `git worktree remove --force` +
  `git branch -D` (ask before the branch delete — it's destructive).
- Issues are agent-operated territory — log findings freely via `bd create '<title>'`, no owner
  approval needed, unlike `dev/docs/`. (The board was migrated to beads 2026-09-02; old slugs
  map via `dev/docs/board/bd-id-map.tsv`.)

## Where everything lives

- Full history of today's investigation: former board items
  `front-2-re-characterized-diffuse-repartition`, `editor-unatco-repartition-soup-size-unknown`,
  `findbestsplit-divergence-forensic-dive-17-real`, `bspmergecoplanars-8-case-merge-gap-live-traced`
  (in that order), and `unatco-detail-brush-pass-staging-generalized` for the first fix of the day —
  all finished and removed in the 2026-09-02 beads migration; recover any via git history of
  `dev/docs/board/`.
- Live-editor differential tooling: `dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/`
  — actively developed and ported to this containerized environment today (was hardcoded to the
  original developer's own machine path before). Look at existing scripts there for the
  gdb-attach-in-container pattern before writing a new one.
- The reverse-engineered spec of UnrealEd's own behavior (the ground truth every fix here is
  checked against): bd issue `uedcli-613ec6`, design field (`bd show uedcli-613ec6`).
