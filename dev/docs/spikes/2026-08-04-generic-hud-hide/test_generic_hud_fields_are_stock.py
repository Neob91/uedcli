"""Pin for spike 2026-08-04-generic-hud-hide.

The `--game` preview clean question: can the HUD + first-person weapon be hidden with ONLY stock
`Engine.*` fields (no game-specific class/method), so the base driver's `CleanFrameForPreview`
works on any UE1 substrate? The genericity claim rests on every field the candidate clean touches
being declared by an ENGINE class, not added by DeusEx. This test re-asserts that against the
committed `uned/UED22/Engine.u` so a binary/package swap that moves a field out of Engine trips red.

Finding (schema evidence): all of them are own-declared by Engine.PlayerPawn / Engine.Pawn /
Engine.Actor — including `bCheatsEnabled`, which UedPreviewLink.uc's header calls "a Deus-Ex-added
field on this install's Engine.PlayerPawn". It is NOT DeusEx-added: it is a stock Engine field.

Being stock is necessary but NOT sufficient for a clean frame: the render half of the spike shows
`myHUD=None` does not hide the DeusEx HUD (DeusEx draws its HUD through `rootWindow`, not the stock
`myHUD.PostRender` path). See findings.md.

This lives in the spike dir (not folded into uedcli/tests/test_engine_facts.py) because editing that
tracked file needs the owner's yes; run it directly:  bin/test dev/docs/spikes/2026-08-04-generic-hud-hide/
"""
from __future__ import annotations

from pathlib import Path

from uedcli import upackage, uprops

ENGINE_U = Path(__file__).resolve().parents[4] / "uned" / "UED22" / "Engine.u"

# field -> the Engine class that must OWN-declare it (own = not inherited).
STOCK_OWNERS = {
    "myHUD": "PlayerPawn",
    "FlashScale": "PlayerPawn",
    "FlashFog": "PlayerPawn",
    "DesiredFlashScale": "PlayerPawn",
    "bCheatsEnabled": "PlayerPawn",   # NB: the link header wrongly calls this DeusEx-added
    "Weapon": "Pawn",
    "bBehindView": "Pawn",
    "EyeHeight": "Pawn",
    "BaseEyeHeight": "Pawn",
    "Physics": "Actor",
    "bHidden": "Actor",
    "bCollideWorld": "Actor",
}


def test_generic_clean_fields_are_all_stock_engine_declarations():
    pkg = upackage.load_package(str(ENGINE_U))
    owned: dict[str, set[str]] = {}
    for cls in ("PlayerPawn", "Pawn", "Actor"):
        props = uprops.own_class_properties(pkg, cls, owner_fqcn=f"Engine.{cls}")
        owned[cls] = {p.name for p in props}

    misplaced = {
        field: expect
        for field, expect in STOCK_OWNERS.items()
        if field not in owned[expect]
    }
    assert not misplaced, (
        "these fields are no longer own-declared by their expected stock Engine class "
        f"(the genericity claim breaks): {misplaced}"
    )
