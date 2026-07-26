#!/usr/bin/env python3
"""LevelInfo extraction spike (2026-06-18). Reads the Unreal package header (Names table)
of a real DeusEx `.dx` WITHOUT a live editor and reports which LevelInfo-class property
names and which volatile names are present, plus whether the level's level-info actor is the
stock `LevelInfo` or the DeusEx `DeusExLevelInfo` subclass.

This is the EVIDENCE for dev/docs/specs/2026-06-18-uedcli-levelinfo-extraction-design.md.

NOTE: the Names table is package-wide (zone-info actors share names like AmbientBrightness),
so a present name is INDICATIVE that the level authored it, not proof. The authoritative field
list comes from Engine/LevelInfo.UC (UCC `batchexport Engine.u Class UC`, captured alongside).
A full authored LevelInfo block could NOT be exported in this environment: every real map
fails UCC `batchexport` (and live MAP LOAD) on a MISSING stock DeusEx content package
(CoreTexMetal, Effects, NewYorkCity, ...) — those packages are not in the dx_lum repo.

Usage: python3 scan_levelinfo_names.py <map.dx> [...]
"""
from __future__ import annotations

import struct
import sys

# var() (editable / authored) LevelInfo + inherited ZoneInfo fields worth preserving.
AUTHORED = {
    "TimeDilation", "Title", "Author", "IdealPlayerCount", "RecommendedEnemies",
    "RecommendedTeammates", "LevelEnterText", "LocalizedPkg", "VisibleGroups",
    "bLonePlayer", "bHumansOnly", "Song", "SongSection", "CdTrack", "PlayerDoppler",
    "Brightness", "Screenshot", "DefaultTexture", "bNeverPrecache", "DefaultGameType",
    # inherited ZoneInfo (var()):
    "ZoneGravity", "AmbientBrightness", "AmbientHue", "AmbientSaturation",
    "FogColor", "FogDistance", "TexUPanSpeed", "TexVPanSpeed", "EnvironmentMap",
    "bWaterZone", "bFogZone", "ZoneName", "ZoneTag",
}
# Computed/volatile (transient/native/runtime) — must be stripped before diffing.
VOLATILE = {
    "TimeSeconds", "Summary", "Region", "OldLocation", "AIProfile", "Pauser",
    "bBegunPlay", "Year", "Month", "Day", "DayOfWeek", "Hour", "Minute", "Second",
    "Millisecond", "NavigationPointList", "PawnList", "Game", "ComputerName",
    "EngineVersion", "EngineRevision", "EngineArchitecture", "AvgAITime",
}


def read_index(b: bytes, off: int) -> tuple[int, int]:
    """Unreal (UE1) compact signed index decode. First byte: bit7=sign, bit6=continue,
    low6=value; following bytes: bit7=continue, low7=value."""
    v = b[off]; off += 1
    is_negative = v & 0x80
    result = v & 0x3F
    shift = 6
    if v & 0x40:
        while True:
            x = b[off]; off += 1
            result |= (x & 0x7F) << shift
            shift += 7
            if not (x & 0x80):
                break
    return (-result if is_negative else result), off


def read_names(data: bytes) -> list[str]:
    _flags, name_count, name_off, *_ = struct.unpack_from("<IiIiIiI", data, 8)
    off = name_off
    names: list[str] = []
    for _ in range(name_count):
        length, off = read_index(data, off)
        names.append(data[off:off + length - 1].decode("latin1"))
        off += length
        off += 4  # object flags (uint32)
    return names


def main(paths: list[str]) -> int:
    for path in paths:
        data = open(path, "rb").read()
        version = struct.unpack_from("<H", data, 4)[0]
        names = set(read_names(data))
        level_info_class = (
            "DeusExLevelInfo" if "DeusExLevelInfo" in names
            else "LevelInfo" if "LevelInfo" in names
            else "?"
        )
        print(f"== {path} (package version {version}) ==")
        print(f"   level-info class : {level_info_class}")
        print(f"   authored present : {sorted(AUTHORED & names)}")
        print(f"   volatile present : {sorted(VOLATILE & names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["Maps/20_Downtown.dx"]))
