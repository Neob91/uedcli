"""Version info + pathing-related exports of the editor (UED22) vs game (DX 1112fm) DLLs."""
import re
import sys
import pefile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import ASSET_ROOT  # noqa: E402
MAIN = str(ASSET_ROOT)
DLLS = [f"{MAIN}/uned/UED22/Engine.dll", f"{MAIN}/dev/games/deusex/System/Engine.dll",
        f"{MAIN}/dev/games/deusex/System/DeusEx.dll", f"{MAIN}/uned/UED22/Editor.dll",
        f"{MAIN}/dev/games/deusex/System/Editor.dll"]
PAT = re.compile(r"Path|Reach|Nav|Scout|reachable|ReachSpec|Route|prune|Prune|Inventory|Warp|Lift|Teleport", re.I)

for p in DLLS:
    pe = pefile.PE(p, fast_load=False)
    ver = {}
    try:
        for fi in pe.FileInfo:
            for e in fi:
                if hasattr(e, "StringTable"):
                    for st in e.StringTable:
                        for k, v in st.entries.items():
                            ver[k.decode()] = v.decode()
    except Exception as ex:
        ver["err"] = str(ex)
    exps = [(e.name.decode(), e.address) for e in pe.DIRECTORY_ENTRY_EXPORT.symbols if e.name] if hasattr(pe, "DIRECTORY_ENTRY_EXPORT") else []
    print("==", p, "base", hex(pe.OPTIONAL_HEADER.ImageBase), "exports", len(exps))
    print("   ver:", {k: v for k, v in ver.items() if k in ("FileVersion", "ProductVersion", "ProductName", "FileDescription")})
    for n, a in sorted(exps, key=lambda x: x[1]):
        if PAT.search(n):
            print(f"   {a:#08x} {n}")
