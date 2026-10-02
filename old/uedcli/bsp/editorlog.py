"""Parse the editor's `MAP REBUILD` log — the build-output BSP health check.

The editor confesses every face it drops and every defect it finds during a rebuild.
`parse_build_log(text) -> BuildLog` reads these channels (Editor.dll wide strings, confirmed
flushing under `MAP REBUILD`):

  FPoly::CalcNormal: Zero-area polygon             -> a dropped face (zero area)
  FPoly::Finalize: Not enough vertices (%i)        -> a dropped face (<3 verts after cleanup)
  BspValidateBrush linked %i of %i polys           -> linked<total => not watertight (leak/hole)
  bspAddNode: Infinitesimal polygon %i (%i)        -> a phantom/sliver node (invisible-wall candidate)
  Processed %i T-points, linked: %i/%i sides       -> total-linked => unlinked T-junctions (HoM)
  Nodes: %i -> %i / Portalized: ... %i leaves, %i nodes  -> final structure (sanity)

Promoted byte-for-byte (parser + channels) from `dev/docs/spikes/bspspike/bsp_editorlog.py`,
validated live 2026-06-24 (caught an injected open-box hole). The parser is source-agnostic —
the same channels were confirmed on real UCC stdout too — but here it reads the ephemeral editor's
own `Editor.log` (`flush_and_parse_since`), which is what materialize drives.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

_RE_ZERO_AREA = re.compile(r"FPoly::CalcNormal: Zero-area polygon")
_RE_FEW_VERTS = re.compile(r"FPoly::Finalize: Not enough vertices \((\d+)\)")
_RE_VALIDATE = re.compile(r"BspValidateBrush linked (\d+) of (\d+) polys")
_RE_INFINITESIMAL = re.compile(r"bspAddNode: Infinitesimal polygon (\d+) \((\d+)\)")
_RE_TPOINTS = re.compile(r"Processed (\d+) T-points, linked: (\d+)/(\d+) sides")
_RE_NODES = re.compile(r"Nodes: (\d+) -> (\d+)")
_RE_PORTAL = re.compile(r"Portalized:.*?(\d+) leaves, (\d+) nodes")


@dataclass(frozen=True, kw_only=True)
class BuildLog:
    """What the editor's rebuild log says it dropped/built. Counts only — no face identity."""
    zero_area_drops: int = 0                          # dropped faces (zero area)
    few_vert_drops: tuple[int, ...] = ()             # dropped faces (the reported vert counts)
    unwatertight: tuple[tuple[int, int], ...] = ()   # (linked, total) where linked < total
    infinitesimal_nodes: int = 0                     # phantom/sliver nodes
    unlinked_tpoints: int = 0                        # T-junction sides the editor could NOT link (HoM)
    final_nodes: int | None = None
    leaves: int | None = None

    @property
    def has_drops(self) -> bool:
        return bool(self.zero_area_drops or self.few_vert_drops or self.unwatertight)

    @property
    def has_holes_or_hom(self) -> bool:
        return self.has_drops or self.unlinked_tpoints > 0

    def findings(self) -> list[str]:
        out = []
        if self.zero_area_drops:
            out.append(f"{self.zero_area_drops} zero-area face(s) dropped (hole/HOM)")
        for v in self.few_vert_drops:
            out.append(f"face dropped: only {v} vertices after cleanup (hole/HOM)")
        for linked, total in self.unwatertight:
            out.append(f"brush not watertight: linked {linked} of {total} polys (leak/hole)")
        if self.unlinked_tpoints:
            out.append(f"{self.unlinked_tpoints} unlinked T-junction side(s) (HoM crack)")
        if self.infinitesimal_nodes:
            out.append(f"{self.infinitesimal_nodes} infinitesimal node(s) (invisible-wall candidate)")
        return out


def parse_build_log(text: str) -> BuildLog:
    """Parse a `MAP REBUILD` log slice into a BuildLog. Pure; offline-testable."""
    few = tuple(int(m.group(1)) for m in _RE_FEW_VERTS.finditer(text))
    unwater = tuple((int(a), int(b)) for a, b in
                    (m.groups() for m in _RE_VALIDATE.finditer(text)) if int(a) < int(b))
    tpts = sum(int(t) - int(l) for _, l, t in
               (m.groups() for m in _RE_TPOINTS.finditer(text)))
    nodes = _RE_NODES.findall(text)
    portal = _RE_PORTAL.search(text)
    return BuildLog(
        zero_area_drops=len(_RE_ZERO_AREA.findall(text)),
        few_vert_drops=few,
        unwatertight=unwater,
        infinitesimal_nodes=len(_RE_INFINITESIMAL.findall(text)),
        unlinked_tpoints=tpts,
        final_nodes=int(nodes[-1][1]) if nodes else (int(portal.group(2)) if portal else None),
        leaves=int(portal.group(1)) if portal else None,
    )


def flush_and_parse_since(driver, offset: int, *, settle: float = 2.0) -> BuildLog:
    """Read the editor log written since `offset` and parse it. `Editor.log` is 4 KB-buffered
    and flush-laggy, so force a flush before reading: settle, dismiss any GC dialog, then a noisy
    `OBJ LIST CLASS=Class` (guaranteed-large output pushes the rebuild lines out of the buffer),
    settle again, read. The caller has already driven `MAP REBUILD` (materialize's build step)."""
    time.sleep(settle)
    driver.dismiss_blocking_dialog()
    driver.exec("OBJ LIST CLASS=Class")
    time.sleep(1.5)
    return parse_build_log(driver.read_log_since(offset))
