#!/usr/bin/env python3
"""EXP2: ACTOR SET on the LevelInfo, using its ACTUAL name; and test SELECTNAME
forms. Also test whether the IMPORTADD 'replace' in exp1 depended on name match.
"""
import re
import sys
import lidrv as L


def li_name(t3d):
    m = re.search(r"Begin Actor Class=(?:DeusEx)?LevelInfo Name=(\S+)", t3d)
    return m.group(1) if m else None


def show(tag, t3d):
    print(f"\n===== {tag}: headers={L.all_actor_headers(t3d)} =====", flush=True)
    print(L.levelinfo_block(t3d), flush=True)


try:
    # Fresh level; find the actual LevelInfo name first.
    L.ex("MAP NEW")
    cur = L.export("c_before")
    name = li_name(cur)
    print(f"[C] actual LevelInfo name on this MAP NEW = {name}", flush=True)

    # SELECTNAME with the ACTUAL name, then ACTOR SET.
    L.ex(f"SELECTNAME NAME={name}")
    # confirm selection via EDIT COPY
    rc = L.subprocess.run(L.WCTL + ["edit-copy"], capture_output=True, text=True)
    L.time.sleep(L.DELAY)
    sel = sorted(set(re.findall(r"Begin Actor .*?Name=(\S+)", rc.stdout)))
    print(f"[C] selection after SELECTNAME {name}: {sel}", flush=True)

    for cmd in [
        f'ACTOR SET Title "InPlaceTitle"',
        f'ACTOR SET Author "ipAuthor"',
        f"ACTOR SET AmbientBrightness 77",
    ]:
        L.ex(cmd)
    after = L.export("c_after")
    show(f"C after SELECTNAME {name} + ACTOR SET", after)

    print("\nDONE exp2", flush=True)
except L.EditorDead as e:
    print(f"*** EDITOR DIED: {e}", flush=True)
    sys.exit(1)
