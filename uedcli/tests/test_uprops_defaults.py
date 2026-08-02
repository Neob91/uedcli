"""Class-default decoding — the SerializeExpr walker + UClass-tail defaults (spec §5.2).

The corpus-integrity and value-oracle tests need the REAL v68 game `.u` install (the games
config paths), so they are integration-marked (deselected by default). The pinned facts:

- WALKER INTEGRITY: every class in every v68+ `.u` on the deusex search path walks its script,
  parses the UState/UClass tail, and lands the defaults tagged-list EXACTLY at the body end
  (`class_default_tags` raises on any desync — the no-fallback contract). First full run
  2026-07-18: 1914/1914 classes clean.
- VALUE ORACLES: `Engine.Light` defaults `LightPeriod=32`/`LightType=LT_Steady`/
  `Texture=Texture'Engine.S_Light'` (live editor-export evidence, 2026-07-14 H3 item +
  UnrealEd property browser); `DeusEx.Greasel` `InitialAlliances(0)` mixed-kind struct.
- NEGATIVE FACT: the shipped v68 ScriptText carries NO defaultproperties block (live-verified
  2026-07-18) — the rejected textual route (spec §5.2) was impossible, not merely second-best.
"""
from __future__ import annotations

import glob
import os

import pytest

from uedcli import config, uprops

pytestmark = pytest.mark.integration


def _resolver():
    # conftest points $UEDCLI_HOME at a tmp dir for isolation; an INTEGRATION test wants the
    # developer's REAL games config, so read it by explicit path (read-only).
    uc = config.load_user_config(override=os.path.expanduser("~/.uedcli/config.toml"))
    if uc is None:
        pytest.skip("no ~/.uedcli games config")
    sub = uc.games.get("deusex")
    if sub is None:
        pytest.skip("no [games.deusex] in the games config")
    paths = [d for d in sub.paths.split(":") if d]
    if not paths:
        pytest.skip("no deusex paths in the games config")

    def resolve(pkg: str):
        want = (pkg + ".u").lower()
        for d in paths:
            for cand in glob.glob(os.path.join(d, "*.u")):
                if os.path.basename(cand).lower() == want:
                    return cand
        return None
    return resolve, paths


def test_walker_corpus_every_class_lands_clean():
    resolve, paths = _resolver()
    total = 0
    for d in paths:
        for path in sorted(glob.glob(os.path.join(d, "*.u"))):
            pkg = uprops.load_package(path)
            if pkg.version < 68:
                continue
            for cls in uprops.iter_classes(pkg):
                uprops.class_default_tags(pkg, cls)      # raises SchemaError on any desync
                total += 1
    assert total > 1000                                  # the DX install has ~1900 classes


def test_defaults_render_corpus_clean():
    resolve, paths = _resolver()
    pkgs: dict = {}
    total = 0
    for d in paths:
        for path in sorted(glob.glob(os.path.join(d, "*.u"))):
            pkg = uprops.load_package(path)
            if pkg.version < 68:
                continue
            pkgs.setdefault(pkg.name, pkg)
            for cls in uprops.iter_classes(pkg):
                fqcn = f"{pkg.name}.{cls}"
                schema = {p.name.casefold(): p for p in uprops.resolve_class_properties(
                    fqcn, resolver=resolve, _cache=pkgs)}
                uprops.resolve_class_defaults(fqcn, resolver=resolve, schema=schema,
                                              _pkgs=pkgs)
                total += 1
    assert total > 1000


def test_pinned_light_and_greasel_oracles():
    resolve, _paths = _resolver()
    d = uprops.resolve_class_defaults("Engine.Light", resolver=resolve)
    assert d[("lightperiod", 0)] == "32"
    assert d[("lighttype", 0)] == "LT_Steady"
    assert d[("texture", 0)] == "Texture'Engine.S_Light'"
    assert d[("lightbrightness", 0)] == "64"
    assert ("lightphase", 0) not in d                    # default IS zero → absent (sparse diff)
    assert d[("mass", 0)] == "100"                       # inherited from Engine.Actor
    g = uprops.resolve_class_defaults("DeusEx.Greasel", resolver=resolve)
    assert g[("initialalliances", 0)] == "(AllianceName=Karkian,AllianceLevel=1,bPermanent=True)"


def test_scripttext_has_no_defaultproperties_block():
    """Negative fact, live-verified 2026-07-18: the shipped v68 `.uc` ScriptText ENDS at the
    `#exec` directives — it carries NO defaultproperties block (checked across Engine + DeusEx
    classes). This empirically vindicates the dev/docs/direction/packages.md 2026-07-18 10:02 §5 choice of the
    BINARY route: the rejected ScriptText-parsing route was not merely second-best, it was
    impossible. (The remaining value oracles are the pinned editor-export fixtures above and
    the live partial-value probe — spikes/2026-07-18-partial-value-import-semantics/ — whose
    export omissions match the decoded defaults member-for-member.)"""
    resolve, _paths = _resolver()
    checked = 0
    for fqcn in ("Engine.Light", "Engine.Brush", "DeusEx.Rat", "DeusEx.Greasel"):
        pkg_name, cls = fqcn.split(".", 1)
        path = resolve(pkg_name)
        if path is None:
            continue
        pkg = uprops.load_package(path, name=pkg_name)
        src_text = uprops._class_script_source(pkg, cls)
        if src_text is None:
            continue
        assert "defaultproperties" not in src_text.lower(), fqcn
        checked += 1
    assert checked >= 3
