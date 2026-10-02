+++
priority = "p2"
kind = "debug"
summary = "docker mount-source permission fails from main checkout; worktree only avoids it by accident (umodel_dir path collision)"
+++

# docker mount-source permission fails from main checkout; worktree only avoids it by accident

Found while running `parity_report.py` (breadth golden-generation task, 2026-08-31). From the main
checkout (`/workspace/uedcli` cwd), every editor-driving command fails with:

```
Error response from daemon: error while creating mount source path '/workspace/umodel_win32':
mkdir /workspace/umodel_win32: permission denied
```

**Root cause, confirmed live.** `tool_assets.umodel_dir()` = `tool_root().parent / "umodel_win32"`,
and `tool_root()` is package-relative (`Path(__file__).resolve().parent.parent`) — deliberately a
SIBLING of the tool dir, not inside it (its own docstring: "deliberately escapes the package-relative
anchor"). Run from the main checkout, `tool_root()` = `/workspace/uedcli`, so `umodel_dir()` =
`/workspace/umodel_win32` — a valid symlink to `dev/games/.cache/umodel-src` (`agent`-owned, `agent`
can `mkdir` under `/workspace` directly). Docker here is rootless (`docker info` shows `rootless`,
root dir `/home/rootless/.local/share/docker`) — the daemon process itself runs as a different OS
user (`rootless`), not `agent`. When it builds the bind mount it apparently doesn't accept the
existing symlink as satisfying its "does the mount source exist" check and tries to `mkdir` a real
directory at that exact path instead, which needs write on the PARENT (`/workspace`, `agent:dialout`
mode `0755` — no group/other write) that the `rootless` user lacks. Reproduced 2/2 tries from the
main checkout; not transient.

**Why a worktree avoids it — by accident, not by design.** `tool_root()` for code loaded from a
worktree is the worktree dir itself, so `umodel_dir()` resolves to `.claude/worktrees/umodel_win32` —
a SHARED path one level up from every worktree, not the symlink. It already exists as a real,
populated directory (`umodel.exe` etc., dated Aug 24 19:08 — created by some earlier worktree
session, `agent`-owned, mode `0755`). Since it already exists, the daemon never needs to `mkdir`
anything and the bug never fires. This is incidental: every worktree session on this box shares that
one `.claude/worktrees/umodel_win32` directory regardless of which worktree it's actually in, which
also means a worktree's umodel install can silently diverge from the main checkout's
(`dev/games/.cache/umodel-src`) — two different physical installs, picked by cwd/import location, with
no signal when they disagree.

**Not fixed here** — this touches `uedcli/stub.py`/`tool_assets.py`, shared container-driving
infrastructure used by much more than this task; out of scope to fix blind. Options for whoever picks
this up: (a) make `/workspace` group/other-writable so the rootless daemon's user can create mount
sources there (a host-level fix, not a uedcli code change), (b) have `ephemeral_build_container`'s
mount-source handling pre-resolve/pre-create symlink targets before handing them to `docker run`
so a symlink source never needs the daemon to `mkdir` at all, or (c) stop deliberately escaping the
package-relative anchor for `umodel_dir()` so it can't land on a shared, ownership-ambiguous path.
Workaround used for this task: run from a worktree instead of the main checkout — reliably sidesteps
the bug, confirmed live (cache-hit and cache-miss/fresh-build runs both succeeded from
`.claude/worktrees/agent-abddd804d64aa0cd6/`).
