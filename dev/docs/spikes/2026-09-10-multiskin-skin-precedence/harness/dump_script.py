"""Dump a class's stored UnrealScript source (`UClass::ScriptText`) out of a `.u`.

    python3 dump_script.py <pkg.u> <ClassName>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from uedcli.upackage import load_package  # noqa: E402
from uedcli.uprops import uclass  # noqa: E402

pkg = load_package(sys.argv[1])
src = uclass._class_script_source(pkg, sys.argv[2])
print(src or "<no ScriptText>")
