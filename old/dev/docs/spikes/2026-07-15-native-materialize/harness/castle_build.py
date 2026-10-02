"""Shared loader for the byte-identity ordered-diff harness (node/pool/surf).

Builds the castle Model TWO ways and hands both to the section diff tools:

  * NATIVE  — the flagged incremental byte-identity core
              (`uedcli_native.build_geometry_bspcsg`), the path we are driving
              toward node-for-node parity.  It is built from the castle trunk's
              brush inputs, serialized, and re-parsed with `umodel.parse_model_body`
              so both sides are the SAME `Model` dataclass.
  * EDITOR  — the golden `Test_Castle.dx` UnrealEd built (the parity target),
              its largest `Model` export parsed with the same parser.

`load_both()` returns `(native_model, editor_model, editor_pkg)`; the package is
returned alongside so surf texture object-refs can be resolved to names
(`pkg.name_of_ref`).  Keeping the build/load in one place means each diff script's
`main()` stays a thin wrapper and a future test can build the models once.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

from uedcli import trunk  # noqa: E402
from uedcli.native import materialize as M, umodel as UM  # noqa: E402
import uedcli_native  # noqa: E402
import utexture_decode as UT  # noqa: E402

TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"


def build_native(trunk_dir: str = TRUNK) -> UM.Model:
    """Build the castle Model via the flagged bspcsg core and re-parse it to a `Model`."""
    lvl, _ = trunk.read_level(Path(trunk_dir))
    brush_order = [n for n in lvl.order if lvl.actors[n].brush is not None]
    bs = [M._build_brush_input(n, lvl.actors[n]) for n in brush_order]
    native = uedcli_native.build_geometry_bspcsg(bs)
    body = uedcli_native.serialize_model(native)
    return UM.parse_model_body(body, 0, len(body))


def load_editor(path: str = EDITOR):
    """Return (editor_model, package) — the golden UnrealEd-built Model + its package
    (needed to resolve surf texture object-refs to names)."""
    pkg = UT.load_package(path)
    mi = max((i for i in range(len(pkg.exports)) if pkg.class_of_export(i) == "Model"),
             key=lambda i: pkg.exports[i]["ssize"])
    e = pkg.exports[mi]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"]), pkg


def load_both(trunk_dir: str = TRUNK, editor_path: str = EDITOR):
    """Return (native_model, editor_model, editor_pkg)."""
    native = build_native(trunk_dir)
    editor, pkg = load_editor(editor_path)
    return native, editor, pkg
