"""Breadth decompile of the whole UED22 CSG/BSP build pipeline (Editor.dll) with angr.

One CFGFast pass (~2m), then Decompiler per target; each output saved as <Name>.decompiled.c
next to this script.  `fn.normalize()` is REQUIRED before Decompiler (its absence fails silently
with a near-empty stub — see findings ledger "Tooling trap").  Output is checked for triviality.

Exported addresses verified against the PE export table 2026-09-02; static (non-exported)
addresses come from the project's prior decodes (bspcsg.rs doc comments / findings ledger).
"""
import sys
from pathlib import Path

import angr
import logging

logging.getLogger("angr").setLevel(logging.ERROR)

OUT = Path(__file__).resolve().parent
DLL = "uned/UED22/Editor.dll"

# name -> VA (base 0x10000000)
TARGETS = {
    # per-brush incremental CSG (Pass 1 / Pass 2)
    "bspBrushCSG": 0x100355E0,          # export
    "bspFilterFPoly": 0x10031F50,       # static (prior decode)
    "FilterEdPoly": 0x10032BF0,         # static
    "FilterLeaf": 0x10033130,           # static
    "AddBrushToWorldFunc": 0x10031770,  # static
    "SubtractBrushFromWorldFunc": 0x100348C0,  # static
    "FilterWorldThroughBrush": 0x10033250,     # static
    "AddWorldToBrushFunc": 0x10031B90,  # static (wtb Add leaf)
    "SubtractWorldToBrushFunc": 0x10034980,    # static (wtb Subtract leaf)
    "bspAddNode": 0x10034E80,           # export
    "bspAddPoint": 0x10035430,          # export
    "bspAddVector": 0x10035530,         # export
    "bspCleanup": 0x10036160,           # export
    "CleanupNodes": 0x10032100,         # static
    "bspValidateBrush": 0x10037290,     # export
    # repartition (bspBuildFPolys -> bspMergeCoplanars -> bspBuild -> bspRefresh)
    "csgRebuild": 0x1004A650,           # export
    "bspRepartition": 0x10049FC0,       # export
    "bspBuildFPolys": 0x10036090,       # export
    "MakeEdPolys": 0x10033BB0,          # static
    "bspMergeCoplanars": 0x10036200,    # export
    "MergeCoplanarPolys": 0x10033CB0,   # static
    "TryToMerge": 0x10034B10,           # static
    "bspBuild": 0x10035EF0,             # export
    "SplitPolyList": 0x10034530,        # static
    "FindBestSplit": 0x100335D0,        # static
    "bspRefresh": 0x10036CD0,           # export
    "bspNodeToFPoly": 0x100365B0,       # export
    "bspUnlinkPolys": 0x100371D0,       # export
}


def main() -> None:
    proj = angr.Project(DLL, auto_load_libs=False)
    print("loaded", proj.arch, hex(proj.loader.main_object.min_addr), flush=True)
    cfg = proj.analyses.CFGFast()
    print("cfg functions:", len(cfg.functions), flush=True)

    for name, addr in TARGETS.items():
        out = OUT / f"{name}.decompiled.c"
        fn = cfg.functions.function(addr=addr)
        if fn is None:
            print(f"{name} NOT FOUND at {hex(addr)}", flush=True)
            continue
        try:
            fn.normalize()
            dec = proj.analyses.Decompiler(fn, cfg=cfg.model)
            text = dec.codegen.text if dec.codegen else ""
        except Exception as e:  # keep going; report at the end
            print(f"{name} FAILED: {e!r}", flush=True)
            continue
        if len(text) < 200:
            print(f"{name} TRIVIAL OUTPUT ({len(text)} bytes) — normalize/resilience trap?", flush=True)
        out.write_text(f"// {name} @ {hex(addr)}  size={fn.size}\n" + text)
        print(f"wrote {out.name} ({len(text)} bytes, fn size {fn.size})", flush=True)


if __name__ == "__main__":
    sys.exit(main())
