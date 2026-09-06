#!/usr/bin/env python3
"""Check every cached editor ref under `_scratch/actor-parity/<level>/` for the two ways it goes stale.

1. **Wrong actor set** -- a `ref_N<n>.dx` must hold the first N actors of the level's trunk, by name.
   A ref left behind by an older or truncated trunk extraction holds a DIFFERENT set, and the ladder
   then reports a divergence that is really a stale file, or passes trivially (board
   `corrupt-trunk-cache-silently-passes-the-ladder`).
2. **Built by a different recipe** -- `build_ued_import_built_golden.py` defines what the reference
   build IS. `actor_parity.build_ref` stamps its digest into a `ref_N<n>.recipe` sidecar; a ref whose
   sidecar is missing or stale came from another recipe. `dbfebf0` (movers get `BasePos`/`BaseRot` in
   the golden's T3D) staled every ref before it, and those fail the gate on names their build never
   had. Copying refs between worktrees loses nothing here -- copy the sidecar too, or rebuild.

Run this before trusting a ladder result built on a seeded or inherited cache.

Usage (venv python):
  verify_refs.py --dx <shipped.dx> [--dx ...] [--delete]

`--delete` removes the refs that fail. Exit code 0 iff no ref is provably stale — a ref of UNKNOWN
recipe is reported but does not fail the run, since deleting a whole inherited cache costs
editor-hours and nothing shows it is wrong.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import actor_parity as ap    # noqa: E402
import parity_gate as pg     # noqa: E402
from uedcli import trunk     # noqa: E402


def ref_export_names(dx: Path) -> set[str]:
    """Every export's name, casefolded. A superset of the ref's actor names (it also holds the
    Model/Polys/Level objects), which is all the comparison needs: a trunk actor name never collides
    with one of those."""
    p = pg.load_package(str(dx))
    names = set()
    for i, e in enumerate(p.exports):
        if e["nm"] >= len(p.names):
            raise SystemExit(f"{dx}: export {i} has out-of-range name index {e['nm']} — corrupt ref")
        names.add(p.names[e["nm"]].casefold())
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dx", action="append", required=True, help="shipped .dx of a ladder level")
    parser.add_argument("--game", default="deusex", help="substrate the trunk is extracted for")
    parser.add_argument("--delete", action="store_true", help="delete refs that do not match")
    args = parser.parse_args()

    bad = unknown = 0
    recipe = ap.recipe_fingerprint()
    for dx in args.dx:
        full, name = ap._resolve_trunk(Path(dx).resolve(), args.game)
        order = trunk.read_level(full)[0].order
        level_dir = ap.ROOT_SCRATCH / name
        for ref in sorted(level_dir.glob("ref_N*.dx")):
            m = re.fullmatch(r"ref_N(\d+)\.dx", ref.name)
            if not m:
                continue                     # variant ref (ref_N59_importadd.dx etc.) -- not a ladder N
            n = int(m.group(1))
            stamp = ref.with_suffix(".recipe")
            if not stamp.exists():
                # Pre-dates the stamp, or was copied without its sidecar. Not provably stale, so it
                # is reported rather than deleted -- rebuilding a whole cache costs editor-hours.
                unknown += 1
                print(f"{name} N={n}: UNKNOWN recipe (no .recipe sidecar)", flush=True)
            elif stamp.read_text().strip() != recipe:
                bad += 1
                print(f"{name} N={n}: STALE -- built by an older golden recipe", flush=True)
                if args.delete:
                    ref.unlink()
                    stamp.unlink()
                continue
            # Both directions: a ref missing an actor is obviously wrong, and one holding an actor
            # from BEYOND the prefix (a ref_N27 filed as ref_N25) is the case that passes trivially.
            got = ref_export_names(ref)
            missing = sorted({a.casefold() for a in order[:n]} - got)
            extra = sorted({a.casefold() for a in order[n:]} & got)
            if missing or extra:
                bad += 1
                why = f"lacks {missing[:4]}" if missing else f"holds later actors {extra[:4]}"
                print(f"{name} N={n}: STALE -- ref {why}", flush=True)
                if args.delete:
                    ref.unlink()
                    stamp.unlink(missing_ok=True)
            else:
                print(f"{name} N={n}: ok", flush=True)
    print(f"=== {bad} stale ref(s), {unknown} of unknown recipe")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
