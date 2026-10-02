"""Pin the empirically-derived UED22 `Base=LevelInfo` MAP-IMPORT stamp rule (spike
2026-09-04-base-stamp-rule).

Runs OFFLINE against two committed artifacts:
  * the editor GOLDEN `../golden/probe_matrix.dx` — UED22's MAP IMPORT+REBUILD+SAVE of the 27-class
    probe matrix; the source of truth for which classes got `Base` stamped;
  * the git-tracked `uned/UED22/*.u` corpus — for each probe class's class-default flags + ancestry.

Asserts the DERIVED predicate reproduces the golden EXACTLY:

    stamped  <=>  bCollideWorld==True  AND  IsA(Engine.Decoration) OR IsA(Engine.Pawn)

(all on class-default values; the actor authoring no `Base`). If a UED22 rebuild changes the stamp
behavior, the re-measured golden diverges from this predicate and the test trips.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
GATE = ROOT / "dev/docs/spikes/2026-09-03-incremental-actor-parity/harness"
HERE = Path(__file__).resolve().parent
for p in (str(ROOT), str(GATE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

GOLDEN = HERE.parent / "golden" / "probe_matrix.dx"
UED22 = ROOT / "uned" / "UED22"

pytestmark = pytest.mark.skipif(not GOLDEN.exists() or not UED22.exists(),
                                reason="probe golden or UED22 corpus not present")


def _measured_stamped() -> dict[str, bool]:
    """Read the golden: probe class -> did UED22 write a `Base` prop on that probe actor."""
    from uedcli.upackage import load_package, read_property_tags
    from parity_gate import Ident, RF_HasStack, _stateframe
    from probe_classes import MOVER_PROBE, PROBES

    p = load_package(str(GOLDEN))
    idt = Ident(p)
    by_name = {p.names[e["nm"]].casefold(): i for i, e in enumerate(p.exports)}
    out: dict[str, bool] = {}
    for name, cls, _note in list(PROBES) + [MOVER_PROBE]:
        i0 = by_name[name.casefold()]                       # KeyError => golden lost a probe: hard fail
        e = p.exports[i0]
        pos, end = e["soff"], e["soff"] + e["ssize"]
        if e["flags"] & RF_HasStack:
            _sf, pos = _stateframe(idt, pos)
        tags, _ = read_property_tags(p, pos, end)
        out[cls] = any(t.name.casefold() == "base" for t in tags)
    return out


def _predicate():
    from uedcli.classdefaults import ClassDefaults
    from uedcli.classindex import ClassIndex
    ufiles = [(f.stem, str(f)) for f in sorted(UED22.glob("*.u"))]
    paths = {s.casefold(): p for s, p in ufiles}
    cd = ClassDefaults(lambda pk: paths.get(pk.casefold()))
    ci = ClassIndex.from_files(ufiles)

    def stamped(cls: str) -> bool:
        bcw = str(cd.for_class(cls).defaults.get(("bcollideworld", 0))) == "True"
        return bcw and (ci.descends_from(cls, "Engine.Decoration")
                        or ci.descends_from(cls, "Engine.Pawn"))
    return stamped


def test_derived_predicate_reproduces_ued22_golden():
    measured = _measured_stamped()
    stamped = _predicate()
    mismatches = {c: (stamped(c), m) for c, m in measured.items() if stamped(c) != m}
    assert not mismatches, f"predicate != golden for: {mismatches}"


def test_key_discriminators_have_expected_outcome():
    """Guard the specific rows that killed the disasm's physics clause and native's bStatic clause,
    so a corpus/golden swap that flips one is caught by name."""
    m = _measured_stamped()
    # physics is irrelevant within the stamped set (disasm's {None,Rotating} refuted):
    assert m["DeusEx.Pinball"] is True         # Deco, PHYS_Falling
    assert m["DeusEx.Poolball"] is True        # Deco, PHYS_Rolling
    assert m["DeusEx.Fish"] is True            # Pawn, PHYS_Swimming
    # bStatic is irrelevant (native's bStatic==False clause refuted):
    assert m["DeusEx.CarWrecked"] is True      # Deco, bStatic=True, bCW=True
    # ancestry gate is real (bCollideWorld==True alone is NOT enough):
    assert m["DeusEx.Spark"] is False          # Effects, bCW=True
    assert m["DeusEx.GasGrenade"] is False     # Projectile, bCW=True
    # bCollideWorld is required (a bCW=False Decoration is NOT stamped):
    assert m["DeusEx.SecurityCamera"] is False # Deco, bCW=False
