"""ULevel body writer — Actors array, FURL, ModelRef, ReachSpecs, trailing block.

Promoted from `level_roundtrip.py` (100/100 byte-exact round-trip).  Section 30.1
pins every field.  A ULevel is a UObject (no StateFrame); its body is:
  <UObject prop list: None terminator>
  i32 Actors.Num, i32 Actors.Max, Num * ci(actor ref)   # TTransArray (raw Num/Max!)
  FURL
  ci ModelRef
  ci ReachSpecs.Count, Count * FReachSpec
  FLOAT TimeSeconds(0), ci FirstDeleted(0),
  16 * ci obj-ref (slot[6]=TextBuffer, else None), ci TravelInfo.Count(0)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .codec import write_ci, write_fstring, enc_i32


@dataclass
class ReachSpec:
    distance: int
    start: int              # object-ref of source NavigationPoint
    end: int                # object-ref of destination
    radius: int
    height: int
    reach_flags: int
    pruned: int = 0


@dataclass
class URL:
    protocol: str = "deusex"
    host: str = ""
    map: str = "Index.dx"
    portal: str = ""
    ops: list = field(default_factory=list)
    port: int = 7790
    valid: int = 1


def write_url(u: URL) -> bytes:
    out = bytearray()
    out += write_fstring(u.protocol)
    out += write_fstring(u.host)
    out += write_fstring(u.map)
    out += write_fstring(u.portal)
    out += write_ci(len(u.ops))
    for op in u.ops:
        out += write_fstring(op)
    out += struct.pack("<ii", u.port, u.valid)
    return bytes(out)


def write_level_body(*, none_index: int, actor_refs: list[int], model_ref: int,
                     url: URL | None = None, reach_specs: list[ReachSpec] | None = None,
                     text_buffer_ref: int = 0) -> bytes:
    """Serialize the ULevel ('MyLevel') object body.  `actor_refs` is the Actors array
    in ITS load-bearing order (index 0 = LevelInfo, 1 = Default Brush)."""
    url = url or URL()
    reach_specs = reach_specs or []
    out = bytearray()
    out += write_ci(none_index)                       # UObject prop list: None
    out += struct.pack("<ii", len(actor_refs), len(actor_refs))   # Num, Max (raw!)
    for r in actor_refs:
        out += write_ci(r)
    out += write_url(url)
    out += write_ci(model_ref)
    out += write_ci(len(reach_specs))
    for rs in reach_specs:
        out += enc_i32(rs.distance) + write_ci(rs.start) + write_ci(rs.end)
        out += struct.pack("<iii", rs.radius, rs.height, rs.reach_flags)
        out += bytes([rs.pruned & 0xFF])
    # trailing block
    out += struct.pack("<f", 0.0)                      # TimeSeconds: 4-byte FLOAT (real maps: ~10..130s)
    out += write_ci(0)                                 # FirstDeleted = None
    for slot in range(16):                             # 16 object refs; slot[6]=TextBuffer
        out += write_ci(text_buffer_ref if slot == 6 else 0)
    out += write_ci(0)                                 # TravelInfo.Count = 0
    return bytes(out)
