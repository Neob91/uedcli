"""Live probe (spec 2026-07-18-actor-prop-subcommands.md §9): does the editor's T3D import
treat members UNMENTIONED in a stored-partial struct value (and elements unmentioned in a
sparse static array) as ZERO or as the CLASS DEFAULT?

Method: import three DeusEx.Rat actors into an ephemeral editor and MAP EXPORT:
  RatA  RotationRate=(Yaw=1234)        — changed member; default (Pitch=4096,Yaw=65530,Roll=3072)
  RatB  RotationRate=(Pitch=4096)      — partial EQUAL to the default member: if import is
                                         member-wise-onto-default the whole value == default and
                                         the export line is ABSENT; if import zero-fills, the
                                         value differs and the line MUST appear. DECISIVE.
  RatC  InitialInventory(1)=(Count=5)  — sparse array write; elements 0/2 default (…,Count=1):
                                         absent from export ⇒ kept default; present ⇒ zeroed.

Run host-native from Tools/uedctl with the LUM project resolvable (cwd repo root).
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from uedctl import config, xfer                                   # noqa: E402
from uedctl.container_assets import resource_mounts               # noqa: E402
from uedctl.driver import Driver                                  # noqa: E402
from uedctl.editor import ensure_editor, stop_editor              # noqa: E402
from uedctl.packages import editor_search_dirs, ensure_load       # noqa: E402
from uedctl.uuid7 import uuid7                                    # noqa: E402

T3D = """Begin Map
Begin Actor Class=DeusEx.Rat Name=RatA
    Location=(X=64.000000,Y=0.000000,Z=0.000000)
    RotationRate=(Yaw=1234)
End Actor
Begin Actor Class=DeusEx.Rat Name=RatB
    Location=(X=128.000000,Y=0.000000,Z=0.000000)
    RotationRate=(Pitch=4096)
End Actor
Begin Actor Class=DeusEx.Rat Name=RatC
    Location=(X=192.000000,Y=0.000000,Z=0.000000)
    InitialInventory(1)=(Count=5)
End Actor
End Map
"""


def main() -> int:
    project = config.resolve_project(env_project=os.environ.get("UEDCTL_PROJECT"),
                                     cwd=os.getcwd())
    user_config = config.load_user_config()
    search_dirs = config.composed_search_dirs(project, user_config)
    mounts = resource_mounts(search_dirs)
    host_dirs = editor_search_dirs(search_dirs)
    state_dir = config.state_dir(project.root, create=True)
    ed_id = uuid7()
    try:
        ed = Driver(container=ensure_editor(ed_id, mounts=mounts, state_dir=state_dir))
        ensure_load(ed, ["DeusEx"], search_dirs=host_dirs, mounts=mounts)
        ed.set_grid(1, 1, 1)
        with tempfile.NamedTemporaryFile("w", suffix=".t3d", delete=False) as f:
            f.write(T3D)
            host_in = f.name
        cin = xfer.cp_in(ed.container, host_in, ext=".t3d")
        ed.map_importadd(cin)
        # IMPORTADD can pop a blocking GC dialog headless (qualify.py's settle recipe);
        # dismiss, then export and POLL for the finished file (exec is fire-and-forget).
        import subprocess
        import time
        ed.dismiss_blocking_dialog()
        ed.map_export("/work/probe_out.t3d")
        text = None
        for _ in range(30):
            time.sleep(1)
            ed.dismiss_blocking_dialog()
            r = subprocess.run(["docker", "exec", ed.container, "cat", "/work/probe_out.t3d"],
                               capture_output=True, text=True, check=False)
            if r.returncode == 0 and "End Map" in r.stdout:
                text = r.stdout
                break
        if text is None:
            raise TimeoutError("MAP EXPORT did not produce a complete file in 30s")
        host_out = host_in + ".out"
        open(host_out, "w", encoding="latin-1").write(text)
    finally:
        stop_editor(ed_id, state_dir)

    for rat in ("RatA", "RatB", "RatC"):
        m = re.search(rf"Begin Actor Class=Rat Name={rat}\b(.*?)End Actor", text, re.DOTALL)
        if m is None:
            print(f"{rat}: NOT FOUND in export")
            continue
        body = m.group(1)
        lines = [ln.strip() for ln in body.splitlines()
                 if "RotationRate" in ln or "InitialInventory" in ln]
        print(f"{rat}: {lines if lines else '(no RotationRate/InitialInventory lines)'}")
    print("\nfull blocks saved:", host_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
