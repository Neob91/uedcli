"""Build the gold (fully-correct) trunk for a task from its tasks/<id>/task.json:
apply every `update(target="corners")` entry's own op, then move every
`anchor` entry by its target anchor's task delta (since in the gold trunk
the anchor's actual delta IS the task delta). `update(target="unchanged")`
entries get no operation -- they stay exactly as the baseline left them.
"""
import os, shutil, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS

WT = str(pathlib.Path(__file__).resolve().parents[3])  # the uedcli checkout -- cwd uedcli needs for `-m uedcli` module resolution

def _main_checkout() -> pathlib.Path:
    """The main checkout's root, resolved via git plumbing (never hardcoded) -- works whether
    WT above is that main checkout or a linked worktree. `--git-common-dir` always resolves to
    the ORIGINAL repo's .git, shared by every worktree; its parent is the main checkout root."""
    common_dir = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                 cwd=WT, capture_output=True, text=True, check=True).stdout.strip()
    return pathlib.Path(common_dir).parent

MAIN_CHECKOUT = _main_checkout()
# The main checkout's venv specifically, not WT's -- a worktree's own .venv/ (if it has one at all)
# has no uedcli_native built; only the main checkout's does.
PY = str(MAIN_CHECKOUT / ".venv" / "bin" / "python")
# The main checkout specifically, not WT's -- dev/games/ is gitignored game content, installed
# once in the main checkout, not replicated per-worktree (same reasoning as PY above).
DX_GAME_DIR = MAIN_CHECKOUT / "dev" / "games" / "deusex"
DX_MAPS_DIR = DX_GAME_DIR / "Maps"
# _scratch/ anywhere in the tree is already gitignored -- reuse that, no new pattern needed.
# eval_runs/ (run_eval.py's subject trunks) lives alongside the base-trunk cache, same reasoning.
BASE_TRUNKS_DIR = pathlib.Path(os.environ.get("BASE_TRUNKS_DIR") or (pathlib.Path(WT) / "dev" / "evals" / "_scratch" / "base_trunks"))

# A dedicated worktree with its OWN isolated .venv + uedcli_native build, used ONLY by
# render_photos.py's `level photo --native` call. MAIN_CHECKOUT's own native extension is a
# SHARED artifact the native-materialize campaign rebuilds constantly (different commit, often a
# different render_frame signature mid-change) -- a render mid-eval can hit it stale or broken by
# unrelated, concurrent work. This worktree is pinned at a fixed commit (detached HEAD) and never
# touched by that campaign; set up once with `git worktree add --detach <path> <known-good commit>`
# then `bin/uedcli --help` in it once to self-provision (.venv + a one-time uedcli_native build).
RENDER_WT = pathlib.Path(os.environ.get("EVAL_RENDER_WT")
                          or (MAIN_CHECKOUT / ".claude" / "worktrees" / "eval-render-frozen"))
RENDER_PY = RENDER_WT / ".venv" / "bin" / "python"

def base_trunk_for(spec: dict) -> pathlib.Path:
    """The task's baseline trunk project. One shared per `dx_map` (sibling tasks on the same
    level -- e.g. all 4 nyc_bar_* tasks -- share one import), cached under BASE_TRUNKS_DIR,
    imported fresh from this checkout's OWN dev/games/deusex/Maps/<dx_map>.dx on first use (a
    few seconds -- see dev/evals/README.md's "Base trunks" section for measured times). Never
    re-imports once the level tree exists; delete the cache project to force a fresh import."""
    proj = BASE_TRUNKS_DIR / spec["dx_map"]
    if (proj / "maps" / spec["level"]).exists():
        return proj
    mapfile = DX_MAPS_DIR / f"{spec['dx_map']}.dx"
    if not mapfile.exists():
        sys.exit(f"{mapfile} not found -- dev/games/deusex isn't set up "
                  f"(see dev/scripts/install-deusex-assets.sh)")
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    r = subprocess.run([PY, "-m", "uedcli", "--project", str(proj), "level", "import",
                        str(mapfile), "--tree", f"level/{spec['level']}"],
                        cwd=WT, capture_output=True, text=True)
    if r.returncode != 0:
        shutil.rmtree(proj, ignore_errors=True)  # don't leave a half-imported cache entry behind
        sys.exit(f"level import failed for {spec['dx_map']} -> level/{spec['level']}: {r.stderr}")
    return proj

def build_gold(task_id: str, out_dir: pathlib.Path):
    spec = TASKS[task_id]
    src = base_trunk_for(spec)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(src, out_dir)
    env = {**os.environ, "UEDCLI_PROJECT": str(out_dir), "UEDCLI_LEVEL": spec["level"]}

    anchor_delta = {}
    for e in spec["entries"]:
        if e.get("kind") != "update" or e.get("target") != "corners":
            continue
        args = [PY, "-m", "uedcli", "brush", "vertex", "move", e["actor"]]
        for corner in e["at"]:
            args += ["--at", ",".join(str(c) for c in corner)]
        args += ["--by", ",".join(str(c) for c in e["delta"])]
        subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
        anchor_delta[e["actor"]] = e["delta"]

    # group `anchor` entries by their actual delta (== their target's task delta) to move in batches
    by_delta = {}
    for e in spec["entries"]:
        if e.get("kind") != "anchor":
            continue
        d = tuple(anchor_delta[e["to"]])
        by_delta.setdefault(d, []).append(e["actor"])
    for delta, actors in by_delta.items():
        args = [PY, "-m", "uedcli", "actor", "move", *actors, "--by", ",".join(str(c) for c in delta)]
        subprocess.run(args, cwd=WT, env=env, check=True, capture_output=True)
    # update(target="unchanged") entries: nothing to do

if __name__ == "__main__":
    task_id = sys.argv[1]
    # resolve to absolute: build_gold()'s subprocess calls run with cwd=WT, so a relative
    # out_dir (as typed at this script's own invocation cwd) would silently resolve against
    # the wrong directory otherwise
    out_dir = pathlib.Path(sys.argv[2]).resolve()
    build_gold(task_id, out_dir)
    print("built gold trunk for", task_id, "->", out_dir)
