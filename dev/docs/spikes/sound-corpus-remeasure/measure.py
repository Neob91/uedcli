#!/usr/bin/env python3
"""Re-measure the SOUND (and .umx music) corpus on uedcli's COMPOSED search path.

Spike: board/to-spike/sound-corpus-remeasure. The old audio-arm design was sized by
numbers taken over dirs the tool does not load. This script measures the truth by
driving the tool's OWN path resolver (`config.composed_search_files`) and enumerating
`Sound` exports with `upackage.load_package`.

It measures only what is actually on the resolved composed path — nothing is walked that
the tool would not load. Point it at a real install with:

    UEDCLI_DX=/path/to/DeusEx python3 measure.py          # explicit install root
    python3 measure.py --config ~/.uedcli/config.toml      # your live config's [games.deusex]

Without an install it prints "corpus not reachable" and exits 0 (the harness is the
deliverable; the numbers come from whoever has the corpus).
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from collections import Counter, defaultdict

# uedcli on sys.path (repo_root/uedcli)
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
sys.path.insert(0, _REPO)

from uedcli import config, upackage  # noqa: E402

# --------------------------------------------------------------------------- composed path

def _compose_from_install(root: str) -> list[tuple[str, str]]:
    """Build the composed load set from a DeusEx install root by writing a throwaway
    games config over its {System,Sounds,Music,Textures} and running the real resolver.

    The wanted sub-dirs are matched against the install's ACTUAL on-disk entry names, taking
    each real dir exactly once. Probing case-variants (`System` and `system`) instead breaks on
    a case-INSENSITIVE host fs (e.g. a Docker Desktop volume): `isdir('System')` is True while
    the real entry is `system`, and listing the same physical dir under two spellings makes the
    fs drop entries. A real case-sensitive Linux install has one spelling and never hits this."""
    wanted = {"system", "sounds", "music", "textures"}
    on_disk = {name.lower(): name for name in os.listdir(root)
               if os.path.isdir(os.path.join(root, name))}
    dirs = [os.path.join(root, on_disk[w]) for w in wanted if w in on_disk]
    paths = ":".join(dirs)
    substrate = config.Substrate(name="deusex", paths=paths)
    user_cfg = config.UserConfig(games={"deusex": substrate}, source="<spike>")
    project = config.Project(root="/", game="deusex")
    return config.composed_search_files(project, user_cfg)


def _compose_from_config(config_path: str) -> list[tuple[str, str]]:
    """Use a live config's [games.*]. Its game is selected by a minimal project naming it."""
    user_cfg = config.load_user_config(config_path)
    if user_cfg is None or not user_cfg.games:
        return []
    game = next(iter(user_cfg.games))
    project = config.Project(root="/", game=game)
    return config.composed_search_files(project, user_cfg)

# --------------------------------------------------------------------------- Sound enumeration

def _sound_exports(pkg: upackage.Package) -> list[tuple[str, str | None]]:
    """(bare_name, dotted_group_path) for every export whose class is `Sound`.
    The dotted path is Package[.Group...].Name; the group is the middle segment(s)."""
    out: list[tuple[str, str | None]] = []
    for i, e in enumerate(pkg.exports, start=1):
        if pkg.object_class_name(i) != "Sound":
            continue
        name = pkg.names[e["nm"]] if 0 <= e["nm"] < len(pkg.names) else "<?>"
        dotted = pkg.object_path(i)
        group = None
        if dotted is not None:
            parts = dotted.split(".")
            if len(parts) >= 3:                      # Package.Group[.Sub].Name
                group = ".".join(parts[1:-1])
        out.append((name, group))
    return out

# --------------------------------------------------------------------------- .umx title sniff

def _umx_title(path: str) -> tuple[str | None, str]:
    """Sniff an embedded tracker-module title out of a .umx by magic. Returns (title, format).
    IT: 'IMPM' at 0, 26-byte song name at +4. S3M: 'SCRM' at +0x2C, 28-byte name at 0.
    XM: 'Extended Module: ' at 0, name at +17 (20 bytes). Else (None, 'unknown')."""
    with open(path, "rb") as f:
        buf = f.read()
    # The module is embedded inside the UE1 package (a Music export's data), so scan for magic.
    it = buf.find(b"IMPM")
    if it != -1:
        name = buf[it + 4:it + 4 + 26].split(b"\x00")[0].decode("latin-1", "replace").strip()
        return (name or None), "IT"
    s3m = buf.find(b"SCRM")
    if s3m != -1 and s3m >= 0x2C:
        name = buf[s3m - 0x2C:s3m - 0x2C + 28].split(b"\x00")[0].decode("latin-1", "replace").strip()
        return (name or None), "S3M"
    xm = buf.find(b"Extended Module: ")
    if xm != -1:
        name = buf[xm + 17:xm + 17 + 20].split(b"\x00")[0].decode("latin-1", "replace").strip()
        return (name or None), "XM"
    return None, "unknown"

# --------------------------------------------------------------------------- report

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="a uedcli config.toml with a [games.*] block")
    ap.add_argument("--root", help="a DeusEx install root (has System/Sounds/Music/Textures)")
    ap.add_argument("--check", action="store_true",
                    help="after measuring, assert the STABLE retail-content facts (see _check); "
                         "exit 3 on drift. Install-layout-dependent totals are reported, not asserted.")
    args = ap.parse_args()

    root = args.root or os.environ.get("UEDCLI_DX")
    if args.config:
        files = _compose_from_config(args.config)
    elif root:
        if not os.path.isdir(root):
            print(f"corpus not reachable: install root does not exist: {root!r}")
            return 0
        files = _compose_from_install(root)
    else:
        print("corpus not reachable: pass --root <install> or UEDCLI_DX=<install> or --config <toml>")
        print("harness is valid; it needs the .uax/.u sound corpus mounted to produce numbers.")
        return 0

    if not files:
        print("corpus not reachable: composed path resolved to ZERO package files.")
        return 0

    print(f"# composed path: {len(files)} package stems\n")

    per_pkg: Counter[str] = Counter()
    groups_per_pkg: dict[str, Counter[str]] = defaultdict(Counter)
    bare_names: list[str] = []
    dupe_names: dict[str, Counter[str]] = defaultdict(Counter)  # per-pkg bare-name collisions
    total = 0
    for path, _prov in files:
        stem = config.pkg_stem(path) or os.path.basename(path)
        try:
            pkg = upackage.load_package(path)
        except upackage.SchemaError as e:
            print(f"  ! skip unreadable: {stem}: {e}", file=sys.stderr)
            continue
        sounds = _sound_exports(pkg)
        if not sounds:
            continue
        per_pkg[stem] = len(sounds)
        total += len(sounds)
        for name, group in sounds:
            bare_names.append(name)
            groups_per_pkg[stem][group or "<root>"] += 1
            dupe_names[stem][name] += 1

    print(f"## TOTAL Sound exports on composed path: {total}\n")
    print("## Sound exports per package (desc):")
    for stem, n in per_pkg.most_common():
        print(f"  {n:6d}  {stem}")

    print("\n## Group (Outer) structure, per package with sounds:")
    for stem, _n in per_pkg.most_common():
        gs = groups_per_pkg[stem]
        shown = ", ".join(f"{g}={c}" for g, c in gs.most_common())
        print(f"  {stem}: {len(gs)} group(s): {shown}")

    # bare-name collisions across groups within one package (identity = Package.Name shard risk)
    print("\n## Bare-name collisions within a package (same Package.Name, different group):")
    any_dupe = False
    for stem, names in dupe_names.items():
        collisions = {n: c for n, c in names.items() if c > 1}
        if collisions:
            any_dupe = True
            print(f"  {stem}: {collisions}")
    if not any_dupe:
        print("  none (every bare name unique within its package)")

    # VO identification: DeusExConAudio* packages, plus name/group heuristics.
    print("\n## VO (voice-over) identification:")
    con_pkgs = {s: n for s, n in per_pkg.items() if s.lower().startswith("deusexconaudio")}
    con_total = sum(con_pkgs.values())
    print(f"  packages named DeusExConAudio*: {len(con_pkgs)}, {con_total} sounds")
    for s, n in sorted(con_pkgs.items()):
        print(f"    {n:6d}  {s}")
    other_vo = {s: n for s, n in per_pkg.items()
                if ("conversation" in s.lower() or s.lower().startswith(("lum_", "tnm")))
                and not s.lower().startswith("deusexconaudio")}
    if other_vo:
        print(f"  other conversation-audio-looking packages: {other_vo}")

    # .umx titles
    print("\n## .umx embedded-title sniff:")
    umx = [p for p, _ in files if p.lower().endswith(".umx")]
    fmt_counter: Counter[str] = Counter()
    for p in sorted(umx):
        title, fmt = _umx_title(p)
        fmt_counter[fmt] += 1
        print(f"  {os.path.basename(p):32s} [{fmt}] title={title!r}")
    print(f"  formats: {dict(fmt_counter)}")

    if args.check:
        return _check(groups_per_pkg, files)
    return 0


# STABLE retail-content facts — the same on any un-modded DX install, so safe to assert.
# (Corpus TOTALS are install-layout-dependent — VO packages may sit in System/ or a backup dir —
#  so they are reported above, never asserted here.)
_GOLDEN_UMX_TITLES = {
    "Area51_Music.umx": ("IT", "Area 51"),
    "Credits_Music.umx": ("IT", "The Illuminati"),
    "Area51Bunker_Music.umx": ("IT", "Begin the End"),
}
_GOLDEN_DEUSEXSOUNDS_GROUPS = {
    "Weapons": 91, "Generic": 85, "Animal": 57, "Player": 56, "Robot": 40,
    "Special": 38, "UserInterface": 17, "Augmentation": 7, "Pickup": 5, "NPC": 3,
}


def _check(groups_per_pkg: dict, files: list[tuple[str, str]]) -> int:
    fails: list[str] = []
    by_base = {os.path.basename(p): p for p, _ in files}
    for base, (want_fmt, want_title) in _GOLDEN_UMX_TITLES.items():
        if base not in by_base:
            fails.append(f"{base}: not on composed path")
            continue
        title, fmt = _umx_title(by_base[base])
        if (fmt, title) != (want_fmt, want_title):
            fails.append(f"{base}: got ({fmt!r},{title!r}) want ({want_fmt!r},{want_title!r})")
    umx = [os.path.basename(p) for p, _ in files if p.lower().endswith(".umx")]
    non_it = [b for b in umx if _umx_title(by_base[b])[1] != "IT"]
    if non_it:
        fails.append(f"expected all reachable .umx to be titled IT, non-IT: {non_it}")
    if "DeusExSounds" in groups_per_pkg:
        got = dict(groups_per_pkg["DeusExSounds"])
        if got != _GOLDEN_DEUSEXSOUNDS_GROUPS:
            fails.append(f"DeusExSounds groups: got {got} want {_GOLDEN_DEUSEXSOUNDS_GROUPS}")
    print("\n## --check:")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        return 3
    print("  OK: golden .umx titles, all-IT, and DeusExSounds group structure hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
