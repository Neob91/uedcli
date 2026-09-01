#!/usr/bin/env python3
"""Build `NeonStrata.utx` by driving UnrealEd 2.2 — the same editor `level materialize` drives.

Imports `demo/assets/logo/neon-strata-512.bmp` as a real UE1 texture, then saves the package:

    TEXTURE IMPORT FILE=<bmp> NAME=Strata PACKAGE=NeonStrata GROUP=Neon MIPS=On FLAGS=<PF_Unlit>
    OBJ SAVEPACKAGE PACKAGE=NeonStrata FILE=<NeonStrata.utx>

Both lines run as one `EXEC <file>` batch in an ephemeral editor (uedcli's own driver channel),
the finished `.utx` is streamed out to the game's Textures dir. Re-run to regenerate — the `.utx`
is a build input, not authored by hand.

Ref to use in a build:  NeonStrata.Neon.Strata
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from uedcli import xfer
from uedcli.driver import Driver, to_z_path
from uedcli.editor import ensure_editor, stop_editor
from uedcli.uuid7 import uuid7

# UE1 PolyFlags: PF_Unlit. Set as the texture's default flags so any surface it is applied to
# renders fullbright (a self-lit neon sign) without a light. Not PF_Masked — the logo is opaque.
PF_UNLIT = 0x00400000

BMP = "assets/logo/neon-strata-512.bmp"
OUT = "/workspace/uedcli/dev/games/deusex/Textures/NeonStrata.utx"


def main() -> int:
    here = Path(__file__).resolve().parent
    bmp = here / BMP
    out = Path(OUT)
    if not bmp.is_file():
        print(f"make_utx: missing input BMP: {bmp}", file=sys.stderr)
        return 2

    # Editor writes its crafted engine ini under <state_dir>/tmp/; keep it under the (daemon-visible)
    # workspace, not /tmp.
    state_dir = here / ".uedcli-home" / "make-utx-state"
    state_dir.mkdir(parents=True, exist_ok=True)

    editor_id = uuid7()                                   # our OWN ephemeral editor (D5/D7)
    container = ensure_editor(editor_id, state_dir=state_dir, mounts=None)
    try:
        d = Driver(container)
        # Push the BMP in via `docker exec tee` (Driver.write_work_file), NOT `docker cp`: rootless
        # docker cannot remount the container's `:ro` /stubs mount that a `docker cp` forces, so cp-in
        # fails "remount-ro … operation not permitted" (same reason xfer.cp_out streams via `cat`).
        bmp_c = d.write_work_file(bmp.read_bytes(), ext="bmp")
        utx_c = f"/work/NeonStrata_{uuid.uuid4().hex}.utx"
        d.begin_script()
        d.exec(f"TEXTURE IMPORT FILE={to_z_path(bmp_c)} NAME=Strata "
               f"PACKAGE=NeonStrata GROUP=Neon MIPS=On FLAGS={PF_UNLIT}")
        d.exec(f"OBJ SAVEPACKAGE PACKAGE=NeonStrata FILE={to_z_path(utx_c)}")
        size = d.run_script(produces=utx_c)               # waits for a complete package or raises
        out.parent.mkdir(parents=True, exist_ok=True)
        xfer.cp_out(container, utx_c, str(out))
        print(f"make_utx: wrote {out} ({size} bytes); ref = NeonStrata.Neon.Strata")
    finally:
        stop_editor(editor_id, state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
