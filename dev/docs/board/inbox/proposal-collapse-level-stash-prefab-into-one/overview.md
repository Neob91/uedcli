+++
priority = "p2"
kind = "owner-question"
summary = "Proposal: collapse level/stash/prefab into ONE flat \"tree\" concept — rename the `level` concept → `tree`, a `Trees/{Maps,Stash,Prefabs}/<name>/` layout with an auto-created `Trees/.gitignore` ignoring `Stash/`, `UEDCLI_LEVEL`→`UEDCLI_TREE`, `--target`→`--target-tree` (Andrzej idea, 2026-07-22). MY EVAL: recommend AGAINST the wholesale rename/reorg — the valuable core already shipped and the residual is net-negative"
+++

# Proposal: collapse level/stash/prefab into ONE flat "tree" concept — rename the `level` concept → `tree`, a `Trees/{Maps,Stash,Prefabs}/<name>/` layout with an auto-created `Trees/.gitignore` ignoring `Stash/`, `UEDCLI_LEVEL`→`UEDCLI_TREE`, `--target`→`--target-tree` (Andrzej idea, 2026-07-22). MY EVAL: recommend AGAINST the wholesale rename/reorg — the valuable core already shipped and the residual is net-negative

ALREADY DONE (so this is NOT greenfield): the three share ONE T3D-tree
format (`t3dtree.py`, invariant 2026-07-18 23:01), and "tree" is ALREADY the umbrella — `--tree
KIND/NAME` (KIND ∈ level|stash|prefab) *replaced* `--target` on 2026-07-20 21:30. So
`--target`→`--target-tree` is moot: the flag is `--tree` now, and `--target-tree` would re-introduce
the exact "target" word that was rejected then (source-vs-destination wart + `materialize --out`
collision) plus redundancy (the value already names the kind). Objections to the residual:
**(1) the KIND distinction is load-bearing, not incidental** — same *format*, genuinely different
*kinds*: a **level** materializes to a playable `.dx`/`.unr` (git-tracked domain object), a **stash**
is machine-local throwaway (captured/applied, no world), a **prefab** is a git-committed shareable
library artifact (placed; `packages`+`meta.json` siblings). `level materialize`/`preview` are
level-only *because a stash/prefab has no world to build*. A flat `tree create/materialize/apply`
doesn't erase the kinds — only the word for them — so you'd trade named kinds (clear) for per-verb
"not valid for this kind" errors (worse). **(2) "tree" is already taken:** terminology (2026-06-23)
fixes **T3D tree** = the on-disk directory FORM shared by all three, and **level** = the playable
domain object; renaming level→tree collapses the content/container distinction and makes "tree" mean
both. **(3) moving stash into `Trees/Stash/` erodes the `.uedcli/` safety invariant** (direction.md:
ALL machine-local throwaway — stash, flocks, staging temps, delivered preview maps — sits in ONE
self-ignoring gitignored `.uedcli/`); it splits throwaway state across two homes and swaps a
self-ignoring dir for a tracked dir + carve-out `.gitignore` (more fragile — a mis-edit commits
scratch; the other `.uedcli/` tenants still can't move). **(4) the `Trees/{Maps,Prefabs}/` root
re-forces the parallel tree that the project-layout decision (2026-07-17 20:58) explicitly rejected**
— maps-dir/prefabs-dir are independently-configurable relative paths with defaults *so uedcli can
point at a repo's EXISTING dirs* (LUM already has `Maps/`, `Prefabs/` at their own locations).
**(5) `$UEDCLI_LEVEL` is deliberately a BARE level name** — the ambient default is "which LEVEL am I
editing"; you never ambiently edit a stash/prefab (those are always explicit `--tree stash/x`), so
`$UEDCLI_TREE` (implying `KIND/NAME`) is meaningless as an editing default. SALVAGEABLE: a single
`Trees/` root with an auto-created `.gitignore` is a genuinely nice ergonomic *default* IF decoupled
from forcing the layout AND from moving stash out of `.uedcli/` — but given (3)/(4) probably not worth
the churn. DECIDE-OR-DROP: your call; record in `decisions.md` if you pursue any of it.
