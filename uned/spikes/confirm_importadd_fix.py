#!/usr/bin/env python3
"""Confirm the Brush=-ordering fix on the REAL uedcli path: MAP IMPORTADD.
broken (Brush ref before block) vs fixed (after block) -> rebuild -> giant box.
Self-contained (no cross-module import side effects).
"""
import sys
import select_matrix as M

BREF = "Brush=Model'MyLevel.Brush'"


def variant(name, ref):
    lines = M.emit_map([M.importadd_actor(name, (0, 0, 0))]).splitlines()
    out = []
    for ln in lines:
        if ln.strip() == BREF:           # drop emit's placement; re-add per policy
            continue
        out.append(ln)
        if ref == "after" and ln.strip() == "End Brush":
            out.append(f"    {BREF}")
    if ref == "before":
        for i, ln in enumerate(out):
            if ln.strip().startswith("Begin Brush"):
                out.insert(i, f"    {BREF}"); break
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    for attempt in range(1, 3):
        try:
            results = {}
            for label, name, ref in [("IMPORTADD broken (before)", "IABEF", "before"),
                                     ("IMPORTADD fixed (after)", "IAAFT", "after")]:
                M.restart_editor(); M.clear()
                p = M.put(variant(name, ref), f"ia_{name}")
                M.ex("MAP GRID X=1 Y=1 Z=1"); M.ex(f"MAP IMPORTADD FILE={p}")
                M.ex("MAP REBUILD")
                _, giant = M.probe(name, 2048, (0, 0, 0))
                results[label] = name in giant
                print(f"[{label:26}] giant INSIDE={giant} -> {name} selectable? {name in giant}", flush=True)
            print("\n===== SUMMARY (real IMPORTADD path) =====", flush=True)
            for k, v in results.items():
                print(f"  {k:26} selectable={v}", flush=True)
            sys.exit(0)
        except M.EditorDead as e:
            print(f"*** {e} (attempt {attempt}) ***", flush=True)
            M.capture_crash("iafix")
    sys.exit(1)
