"""Re-assert the PF_FakeBackdrop render facts against the UED22 binaries.

Every fact established by the 2026-09-12 PF_FakeBackdrop RE spike is pinned here as an
exact byte match at an exact RVA, so a different/patched binary trips instead of drifting.

Run: python3 dev/docs/spikes/2026-09-12-pf-fakebackdrop-re/harness/verify_fakebackdrop_facts.py [uned/UED22]
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, "dev/docs/spikes/bspspike")
import pe  # noqa: E402

# (dll, rva, expected bytes, what it proves)
FACTS = [
    # ---- URender::OccludeBsp (render.dll +0x18e10) per-surf flag dispatch ----
    ("render.dll", 0x198B2, "8b 40 04",
     "PolyFlags = Model->Surfs[Node->iSurf].PolyFlags (FBspSurf +0x04)"),
    ("render.dll", 0x198B5, "0b 85 50 f6 ff ff",
     "PolyFlags |= Viewport->ExtraPolyFlags"),
    ("render.dll", 0x19C3D, "8b 85 40 f7 ff ff",
     "load working PolyFlags"),
    ("render.dll", 0x19C43, "84 c0 79 33",
     "test al,al / jns -> the PF_FakeBackdrop (0x80) branch test, encoded as a sign test"),
    ("render.dll", 0x19C4D, "85 c9 0f 85 bb 00 00 00",
     "if (GIsEditor) use the editor's pSkyZoneInfo instead"),
    ("render.dll", 0x19C56, "8b 4f 04 ff 15 8c 43 03 10",
     "ULevel::GetZoneActor(iZone) on Frame->Level"),
    ("render.dll", 0x19C5F, "83 b8 78 02 00 00 00 0f 85 9c 00 00 00",
     "NULL check on AZoneInfo::SkyZone (+0x278); zero -> branch skipped"),
    ("render.dll", 0x19C86, "f7 c1 00 00 00 08 0f 84 3c 03 00 00",
     "PF_Mirror (0x8000000) test, reached only when FakeBackdrop did NOT take"),
    ("render.dll", 0x19C98, "83 78 1c 03 0f 8d 2c 03 00 00",
     "mirror: Frame->Recursion (+0x1c) >= 3 -> skip"),
    ("render.dll", 0x19CA4, "f7 80 7c 04 00 00 00 08 00 00",
     "mirror: ShowFlags (PlayerPawn +0x47c) & 0x800 (SHOW_PlayerCtrl)"),
    ("render.dll", 0x19D24, "83 7f 1c 03 0f 8d 52 ff ff ff",
     "backdrop: Frame->Recursion >= 3 -> fall through to the mirror test"),
    ("render.dll", 0x19D30, "f7 80 7c 04 00 00 00 08 00 00",
     "backdrop: same ShowFlags & 0x800 gate"),
    ("render.dll", 0x19D53, "56 8b 4f 04 ff 15 8c 43 03 10 8b b0 78 02 00 00",
     "backdrop body re-fetches SkyZone = GetZoneActor(iZone)->SkyZone"),
    ("render.dll", 0x19D67, "8d 8d 7c f7 ff ff ff 15 74 42 03 10",
     "SkyCoords = Frame->Coords (FCoords copy ctor)"),
    ("render.dll", 0x19D7E, "8d 8d 7c f7 ff ff ff 15 64 42 03 10",
     "SkyCoords.Origin -= Frame->Coords.Origin (FVector::operator-=)"),
    ("render.dll", 0x19D8A, "8d 86 dc 00 00 00",
     "&SkyZone->Rotation (AActor +0xdc) for FCoords::operator/=(FRotator)"),
    ("render.dll", 0x19D9D, "8d 86 d0 00 00 00",
     "&SkyZone->Location (AActor +0xd0) for FVector::operator+="),
    ("render.dll", 0x19E3D, "0f b6 86 90 00 00 00",
     "child frame iZone = SkyZone->Region.ZoneNumber (AActor +0x90)"),
    ("render.dll", 0x19E55, "ff 52 68",
     "call URender vtable +0x68 = CreateChildFrame"),
    ("render.dll", 0x19E60, "e9 86 09 00 00",
     "backdrop branch jumps past the draw-list emission: the surf is NOT drawn"),
    ("render.dll", 0x19FCE, "f7 c1 00 00 00 04 0f 84 4a 03 00 00",
     "PF_Portal (0x4000000) warp-zone test, the third arm of the same chain"),
    ("render.dll", 0x1A083, "83 78 1c 03",
     "warp zone: the same Frame->Recursion >= 3 guard"),
    ("render.dll", 0x1A324, "f6 c1 01 0f 85 be 04 00 00",
     "PF_Invisible also jumps to the same skip target 0x1a7eb"),
    # ---- URender::CreateChildFrame / CreateMasterFrame: the recursion counter ----
    ("render.dll", 0x14B64, "8b 46 1c 40 89 47 1c",
     "Child->Recursion = Parent->Recursion + 1"),
    ("render.dll", 0x14E13, "c7 47 1c 00 00 00 00",
     "CreateMasterFrame: Recursion = 0"),
    # ---- URender::OccludeFrame / DrawFrame recurse over the child frames ----
    ("render.dll", 0x1AD3E, "8b 77 10 85 f6 74 0d 56 8b cb e8 53 fd ff ff 8b 76 0c",
     "OccludeFrame walks Frame->Child(+0x10)/Sibling(+0xc) and re-enters OccludeFrame"),
    ("render.dll", 0x15110, "8b 76 10 85 f6 74 0e 56 e8 73 ff ff ff 8b 76 0c",
     "DrawFrame draws child frames first, then the frame's own surfaces"),
    # ---- render.dll: PF_Unlit is the ONLY PolyFlag the light manager checks ----
    ("render.dll", 0x7C3B, "8b 4b 10 f7 c1 00 00 40 00",
     "light setup tests PF_Unlit (0x400000) only - PF_FakeBackdrop is not tested"),
    ("render.dll", 0x15690, "83 78 18 ff 74 55",
     "DrawFrame skips the light manager when Surf->iLightMap (+0x18) == INDEX_NONE"),
    # ---- Editor.dll: the lighting build gives a PF_FakeBackdrop surf no lightmap ----
    ("Editor.dll", 0xA4AE7, "f7 47 04 81 00 40 00",
     "lightmap alloc skips PolyFlags & (PF_Invisible|PF_FakeBackdrop|PF_Unlit) = 0x400081"),
    # ---- ShowFlags bit identities, read off the editor's own toggles ----
    ("unrealed.exe", 0x33FFD, "8b 81 7c 04 00 00 83 f0 04",
     "the 'Show Backdrop' toolbar command is ShowFlags ^= 4  => SHOW_Backdrop == 0x4"),
    ("unrealed.exe", 0x33659, "81 b0 7c 04 00 00 00 08 00 00",
     "the 'Realtime Preview' command is ShowFlags ^= 0x800 (the bit OccludeBsp gates on)"),
    ("unrealed.exe", 0x33F89, "f6 46 04 80",
     "the editor's guard scans Surfs for PolyFlags & PF_FakeBackdrop"),
    ("Engine.dll", 0x1402B9, "c7 86 7c 04 00 00 0c 48 00 00",
     "the game viewport's ShowFlags default 0x480c contains 0x800, so the sky always renders"),
    # ---- sizeof(AActor) == 0x20c, which places ZoneInfo.SkyZone (the 28th ZoneInfo var
    #      slot, 0x6c bytes in) at exactly the +0x278 the sky branch dereferences ----
    ("Engine.dll", 0xE4AE3, "68 0c 02 00 00",
     "UClass ctor for AActor is passed InSize = 0x20c; 0x20c + 0x6c == 0x278 == SkyZone"),
]


def main(root=Path("uned/UED22")):
    bad = 0
    for dll, rva, want, why in FACTS:
        path = str(root / dll)
        got = pe.read_at_va(path, pe.image_base(path) + rva, len(want.split()))
        got_s = " ".join(f"{b:02x}" for b in got)
        ok = got_s == want
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {dll} +{rva:#07x}  {why}")
        if not ok:
            print(f"       want {want}\n       got  {got_s}")

    # URender vtable slot +0x68 really is CreateChildFrame.
    p = str(root / "render.dll")
    base = pe.image_base(p)
    slot = struct.unpack("<I", pe.read_at_va(p, base + 0x345E0 + 0x68, 4))[0]
    want_rva = pe.exports(p)[
        "?CreateChildFrame@URender@@UAEPAUFSceneNode@@PAU2@PAVFSpanBuffer@@PAVULevel@@"
        "HHMABVFPlane@@ABVFCoords@@PAUFScreenBounds@@@Z"
    ]
    ok = slot == base + want_rva
    bad += not ok
    print(f"{'ok  ' if ok else 'FAIL'} render.dll URender vtable +0x68 == CreateChildFrame")

    print(f"\n{len(FACTS) + 1 - bad}/{len(FACTS) + 1} facts hold")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("uned/UED22")))
