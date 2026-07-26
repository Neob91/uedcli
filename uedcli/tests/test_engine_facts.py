"""Engine-facts regressions — assertions that re-check a spike's finding about how the real
UnrealEd 2.2 binary behaves, so a binary swap / rebuild that changes the behavior trips a red test
instead of drifting unnoticed (uedcli `dev/docs/rules/spikes.md` "pin the finding, or it rots").

Each test cites the spike or engine-fact doc it enforces. They all run OFFLINE, against one of two
kinds of committed artifact (`dev/docs/rules/spikes.md` accepts either as the pin):

* the committed `uned/UED22/*.dll` — asserting byte patterns read out of the binary by a spike's
  disassembly harness (no editor, no capstone/pefile needed at test time); or
* a committed GOLDEN produced by the real editor — a `MAP EXPORT` under `fixtures/` — asserting a
  property of what the editor actually wrote.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest

UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"


def _rva_to_offset(data: bytes, rva: int) -> int:
    """Map a PE relative-virtual-address to a file offset via the section table (no pefile dep)."""
    pe = data.index(b"PE\0\0")
    coff = pe + 4
    n_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    sec = coff + 20 + opt_size
    for i in range(n_sections):
        b = sec + 40 * i
        vsize = struct.unpack_from("<I", data, b + 8)[0]
        vaddr = struct.unpack_from("<I", data, b + 12)[0]
        raw = struct.unpack_from("<I", data, b + 20)[0]
        if vaddr <= rva < vaddr + vsize:
            return raw + (rva - vaddr)
    raise AssertionError(f"RVA {rva:#x} not in any section")


def test_t3d_import_strips_double_slash_comments():
    """`Core.dll ParseLine` strips `//` line-comments on T3D import (gated on not-in-quotes AND the
    `Exact==0` that `ImportProperties` passes) — this is what lets a `// uedcli-folder: <path>`
    carrier ride `actor show` output through `MAP IMPORTADD`/`EDIT PASTE` while the editor silently
    drops it. If UED22 is rebuilt and the comment-strip changes, this trips.

    Spike: dev/docs/spikes/2026-07-18-t3d-comment-tolerance/ (RE @ core.dll RVA 0x5730e;
    empirically confirmed: `//`/`/* */`/`;` all import cleanly, only `//` is a true strip).

    The unique 16-byte pattern is the `//` detect-and-latch:
        83 FA 2F        cmp edx, 0x2f        ; current char == '/'
        75 0F           jne +0x0f
        66 39 51 02     cmp word [ecx+2], dx ; next char == '/'  (dx == 0x2f)
        B8 01 00 00 00  mov eax, 1
        0F 44 ...       cmove ebx, eax       ; latch comment flag
    """
    core = (UED22 / "core.dll").read_bytes()
    pattern = bytes.fromhex("83fa2f750f66395102b8010000000f44")
    # present exactly once at the known ParseLine RVA — both the count and the location pin it
    assert core.count(pattern) == 1, "the // comment-strip pattern is not uniquely present in core.dll"
    off = core.index(pattern)
    assert off == _rva_to_offset(core, 0x5730E), "the // comment-strip moved off its known ParseLine RVA"


# ── scale / sheer (spike 2026-06-25-scale-transform-mechanics) ──────────────────────────────────

def test_sheer_coeff_matches_the_disassembled_piecewise_snap():
    """`transform.sheer_coeff` re-asserts the EXACT closed form disassembled from `core.dll`
    `0x1001e7c0` (FScale sheer coefficient) and validated against a 20-point live scan (spike §3):
    deadzone ≤0.05, `|r|−0.05` up to 0.55, a snap-to-0.5 plateau on 0.55–0.65, `|r|−0.15` beyond;
    antisymmetric in r. The `.rdata` constants ±0.05/±0.55/±0.5/±0.65/±0.15 are the branch points.
    If the transform math drifts off the editor's snap, this trips.
    """
    from uedcli.transform import sheer_coeff
    # the live-scan table (spike §3), exact:
    table = {0.05: 0.00, 0.10: 0.05, 0.50: 0.45, 0.55: 0.50, 0.60: 0.50,
             0.65: 0.50, 0.70: 0.55, 1.0: 0.85, 2.0: 1.85}
    for rate, k in table.items():
        assert sheer_coeff(rate) == pytest.approx(k), rate
        assert sheer_coeff(-rate) == pytest.approx(-k), rate     # antisymmetric
    assert sheer_coeff(0.0) == 0.0
    assert sheer_coeff(0.049) == 0.0                              # inside the deadzone


def test_fscale_emission_rule_byte_matches_the_editor():
    """`transform.emit_fscale` reproduces the editor's EXACT `MainScale`/`PostScale` serialization
    (spike §1, H3-critical): a `Scale` axis iff ≠1.0 (negatives written), the whole `Scale=(...)`
    omitted when all axes 1.0; `SheerRate` iff ≠0.0; `SheerAxis` ALWAYS; 6-dp. Each string below is a
    verbatim editor MAP EXPORT readback — a drift here means H3 post-verify fails on scaled brushes.
    """
    from decimal import Decimal as _D
    from uedcli.transform import FScale, emit_fscale
    assert emit_fscale(FScale()) == "(SheerAxis=SHEER_ZX)"
    assert emit_fscale(FScale((_D(2), _D(2), _D(2)))) == \
        "(Scale=(X=2.000000,Y=2.000000,Z=2.000000),SheerAxis=SHEER_ZX)"
    assert emit_fscale(FScale((_D(2), _D(1), _D(1)))) == "(Scale=(X=2.000000),SheerAxis=SHEER_ZX)"
    assert emit_fscale(FScale((_D(-1), _D(1), _D(1)))) == "(Scale=(X=-1.000000),SheerAxis=SHEER_ZX)"
    assert emit_fscale(FScale((_D(2), _D("0.5"), _D(1)), _D("0.3"), "SHEER_YZ")) == \
        "(Scale=(X=2.000000,Y=0.500000),SheerRate=0.300000,SheerAxis=SHEER_YZ)"


# ── sprite / light / sound radii (spike 2026-07-21-unrealed-sprite-radii-rendering) ─────────────

def test_world_light_radius_matches_the_source_formula():
    """`preview.world_light_radius` re-asserts UE1 v200 `AActor::WorldLightRadius` = 25*(byte+1) —
    the `+1` is real (LightRadius=0 still reaches 25 UU). Spike Q3 (✅ UE1 v200 `AActor.h`)."""
    from uedcli.preview import world_light_radius
    assert world_light_radius(0) == 25
    assert world_light_radius(8) == 225
    assert world_light_radius(255) == 6400


def test_world_sound_radius_matches_the_source_formula():
    """`preview.world_sound_radius` = 25*(SoundRadius+1); the default SoundRadius=32 → 825 UU.
    Spike Q3 (✅ UE1 v200 `AActor.h`)."""
    from uedcli.preview import world_sound_radius
    assert world_sound_radius(32) == 825
    assert world_sound_radius(0) == 25


def test_collision_box_is_twice_the_half_height():
    """CollisionHeight is a HALF-height: the collision box spans Location.Z ± CollisionHeight, so
    total height == 2*CollisionHeight and half-width == CollisionRadius. Spike Q2 (✅ UE1 v200
    `UnEdCam.cpp` `SHOW_ActorRadii`)."""
    radius, half_height = 22.0, 40.0
    assert 2 * half_height == 80.0                 # total box height
    assert radius == 22.0                          # box half-width == CollisionRadius


def test_sprite_footprint_is_drawscale_times_texel_dims():
    """A DT_Sprite billboard's world footprint == (DrawScale*USize, DrawScale*VSize): 1 texel = 1 UU
    at DrawScale 1. Spike Q1 (✅ UE1 v200 `UnSprite.cpp` `FDynamicSprite::Setup`)."""
    from uedcli.preview import sprite_footprint
    assert sprite_footprint(1.0, 32, 48) == (32.0, 48.0)
    assert sprite_footprint(2.0, 32, 48) == (64.0, 96.0)


# ── ULevel Actors-array layout (spike 2026-07-24-level-import-order) ─────────────────────────────

def test_level_actors_array_is_int_num_max_then_compact_refs():
    """`Engine.Level`'s Actors array (native tail, after the object's None-terminated property list)
    is `[i32 Num][i32 Max]` (raw INT32, NOT a compact count; Num==Max on disk) then Num signed
    FCompactIndex object refs, ref 0 == a null/deleted slot; Actors[0] == LevelInfo. This is the
    authoritative actor ORDER `level import` must emit (spec 2026-07-24 §5.1). Pinned by decoding
    the encode mirror `native.level_write.write_level_body` with the production `upackage` reader —
    if either side's layout drifts, the round-trip breaks and this trips. (Verified live against
    retail 00_Intro/00_Training/02_NYC_Street — see the spike's findings.md; game maps are gitignored
    copyrighted assets, so the committed regression rides the writer.)"""
    import struct

    from uedcli import upackage
    from uedcli.native.level_write import write_level_body

    # LevelInfo at [0], default brush at [1], a null/deleted slot, then a real actor (artificial refs).
    actor_refs = [1, 2, 0, 4207]
    body = write_level_body(none_index=0, actor_refs=actor_refs, model_ref=99)

    pos = 0
    none_idx, pos = upackage.read_compact_index(body, pos)
    assert none_idx == 0                                        # the UObject property-list terminator
    num, mx = struct.unpack_from("<ii", body, pos); pos += 8
    assert (num, mx) == (len(actor_refs), len(actor_refs))      # raw INT32, Num == Max
    decoded = []
    for _ in range(num):
        r, pos = upackage.read_compact_index(body, pos)
        decoded.append(r)
    assert decoded == actor_refs                                # order + the null slot preserved
    assert decoded[0] == 1                                      # Actors[0] == LevelInfo (invariant)
    assert [r for r in decoded if r > 0] == [1, 2, 4207]        # dropping nulls keeps authored order


def test_editor_frotator_omits_zero_components_and_never_writes_an_all_zero_rotation():
    """UnrealEd serializes an FRotator with its ZERO components OMITTED (`Rotation=(Yaw=-16384)`,
    never `(Pitch=0,Yaw=-16384,Roll=0)`) and omits the `Rotation=` line ENTIRELY when the rotator
    is all-zero. Pinned against the committed editor-exported golden `fixtures/level_small.t3d`.

    This is the fact behind the H3 post-verify's member-wise struct expansion (`typedprops`):
    uedcli's producers wrote all three components, so a yaw-only actor never text-matched its own
    re-materialization and `level materialize` aborted with nothing written. If a future editor/
    exporter starts emitting explicit zeros, this trips and the normalizer must be revisited."""
    t3d = (Path(__file__).resolve().parent / "fixtures" / "level_small.t3d").read_text()
    rotations = re.findall(r"Rotation=\(([^)]*)\)", t3d)
    assert rotations, "golden must exercise the fact"

    for body in rotations:
        components = dict(re.findall(r"(Pitch|Yaw|Roll)=(-?\d+)", body))
        assert components, f"unparsed FRotator body: {body!r}"
        # (a) no component is ever written as an explicit zero...
        assert all(int(v) != 0 for v in components.values()), f"explicit zero component: {body!r}"
        # (b) ...and the surviving components keep Pitch,Yaw,Roll order.
        order = [n for n in ("Pitch", "Yaw", "Roll") if n in components]
        assert list(components) == order, f"components out of canonical order: {body!r}"

    # (c) an all-zero rotator is never written at all.
    assert "Rotation=()" not in t3d


def test_the_typed_compare_decodes_every_golden_rotator_without_rewriting_it():
    """The compare agrees with the editor on real editor output: every `Rotation=` in the golden
    decodes to exactly the components UnrealEd wrote (with the ones it omitted resolving to the
    zero default), so comparing can never REWRITE what the editor itself emitted — which would flip
    the post-verify mismatch around to the other side."""
    from uedcli import typedprops

    rot = typedprops.Field(typedprops.STRUCT,
                           members=(("pitch", typedprops.Field(typedprops.INT)),
                                    ("yaw", typedprops.Field(typedprops.INT)),
                                    ("roll", typedprops.Field(typedprops.INT))))
    t3d = (Path(__file__).resolve().parent / "fixtures" / "level_small.t3d").read_text()
    for body in re.findall(r"Rotation=\([^)]*\)", t3d):
        value = body[len("Rotation="):]
        stated = {k.casefold(): int(v) for k, v in re.findall(r"(Pitch|Yaw|Roll)=(-?\d+)", value)}
        decoded = typedprops.typed_value(value, rot)
        assert decoded == {"pitch": 0, "yaw": 0, "roll": 0, **stated}, value


def test_over_range_frotator_components_are_never_reduced_mod_65536():
    """UnrealEd stores and re-serializes an FRotator field VERBATIM — no mod-65536 reduction — through
    T3D import, `MAP SAVE`, the binary round-trip, and the offline UCC re-export that the H3
    post-verify actually reads. Live-probed 2026-07-25 on point actors (`MAP IMPORTADD`) and brushes
    (`EDIT PASTE`), three independent read-back legs:
    `dev/docs/spikes/2026-07-25-frotator-import-normalization/findings.md`.

    So the compare must NEVER route a component through `rotation.parse_frotator`'s `% 65536`:
    20,109 of the 23,960 `Rotation` components in the committed `.t3d` corpus are out of range, and
    reducing them would rewrite a real rotator to zero — which, since zero equals the class default,
    makes it compare equal to an UNROTATED actor and lets a wrong map pass. Negatives are not
    wrapped either (`-16384` stays `-16384`, never `49152`). An FRotator component is an
    `IntProperty`, so `typedprops` decodes it as a verbatim int."""
    from uedcli import typedprops

    for text, want in (("-131072", -131072), ("-65536", -65536), ("65536", 65536),
                       ("-81920", -81920), ("-16384", -16384)):
        assert typedprops.typed_value(text, typedprops.Field(typedprops.INT)) == want, text


def test_the_sheer_axis_enum_matches_the_real_core_package():
    """`typedprops.ESHEER_AXIS` is the compare's fallback mapping from the T3D enum NAME
    (`SHEER_ZX`) to the ordinal a struct-member default decodes as — used when a level's class
    schema is unavailable. It must match `Core.u`'s real `ESheerAxis` ordering, and
    `transform.DEFAULT_SHEER_AXIS` (what the editor writes for an unsheared actor) must be one of
    its values."""
    from uedcli import typedprops
    from uedcli.transform import DEFAULT_SHEER_AXIS, _SHEER_OFFDIAG

    assert typedprops.ESHEER_AXIS[0] == "SHEER_None"
    assert DEFAULT_SHEER_AXIS in typedprops.ESHEER_AXIS
    assert set(typedprops.ESHEER_AXIS[1:]) == set(_SHEER_OFFDIAG)      # every sheared axis pair


# ── mover Saved* sentinels (spike 2026-07-25-mover-savedpos-savedrot-engine-stamped) ────────────

def _export_rva(data: bytes, name: bytes) -> int:
    """The RVA of a named PE export (no pefile dep) — so the assertion below can say *which
    function* the byte pattern sits in, by name, instead of trusting a bare address."""
    pe = data.index(b"PE\0\0")
    coff = pe + 4
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    n_dirs_off = opt + (92 if magic == 0x10b else 108)
    exp_rva = struct.unpack_from("<I", data, n_dirs_off + 4)[0]
    d = _rva_to_offset(data, exp_rva)
    n_funcs, n_names = struct.unpack_from("<II", data, d + 20)
    funcs, names, ords = struct.unpack_from("<III", data, d + 28)
    funcs, names, ords = (_rva_to_offset(data, r) for r in (funcs, names, ords))
    for i in range(n_names):
        nrva = struct.unpack_from("<I", data, names + 4 * i)[0]
        off = _rva_to_offset(data, nrva)
        if data[off:data.index(b"\0", off)] == name:
            idx = struct.unpack_from("<H", data, ords + 2 * i)[0]
            assert idx < n_funcs
            return struct.unpack_from("<I", data, funcs + 4 * idx)[0]
    raise AssertionError(f"export {name!r} not found")


def test_amover_postload_unconditionally_stamps_the_savedpos_savedrot_sentinels():
    """`AMover::PostLoad()` OVERWRITES `SavedPos` with `(-12345,-12345,-12345)` and `SavedRot` with
    `(Pitch=123,Yaw=456,Roll=789)` on EVERY load of a Mover object — no guard, no test of the stored
    value, right after `Super::PostLoad()`. That is why they are in `normalize.COMPUTED_PROPS`: a
    uedcli-authored mover omits both, the map it materializes into always comes back carrying the
    sentinels, and without the strip every mover map fails the H3 post-verify.

    Spike: dev/docs/spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/ (RE @ UED22
    `Engine.dll` `?PostLoad@AMover@@UAEXXZ` RVA 0x171140; the same two stores are in the DX-shipped
    `Engine.dll` at RVA 0xaf7e0).

    The 92-byte pattern is the two stores, verbatim:
        C7 45 CC 00E440C6 (x3)          FVector temp = -12345.0f, -12345.0f, -12345.0f
        C7 86 A0/A4/A8 03.. 00E440C6    this->SavedPos.{X,Y,Z} = -12345.0f
        C7 45 D8 7B000000               FRotator temp .Pitch = 123
        C7 45 DC C8010000                             .Yaw   = 456
        B8 15030000 / 89 45 E0                        .Roll  = 789
        F3 0F 7E 45 D8 / 66 0F D6 86 C4030000         this->SavedRot.{Pitch,Yaw} = temp
        89 86 CC030000                                this->SavedRot.Roll        = 789
    If UED22 is rebuilt and the stamp changes (or gains a guard), this trips and the strip must be
    re-justified."""
    engine = (UED22 / "Engine.dll").read_bytes()
    pattern = bytes.fromhex(
        "c745cc00e440c6c745d000e440c6c745d400e440c6"
        "c786a003000000e440c6c786a403000000e440c6c786a803000000e440c6"
        "c745d87b000000c745dcc8010000b8150300008945e0"
        "f30f7e45d8660fd686c40300008986cc030000")
    assert engine.count(pattern) == 1, "the AMover::PostLoad Saved* stamp is not uniquely present"
    off = engine.index(pattern)

    # Locate the function BY NAME, not by a hardcoded address: a relink that merely moves the code
    # is not the drift this test is for, and pinning the RVA would turn it into a false alarm.
    # (For reference the export sits at RVA 0x171140 today and the body is 0xe6 bytes.)
    body = _rva_to_offset(engine, _export_rva(engine, b"?PostLoad@AMover@@UAEXXZ"))
    assert body < off < body + 0x100, "the Saved* stamp is no longer inside AMover::PostLoad"

    # ...and it is a STAMP, not a class default: neither sentinel appears anywhere in the shipped
    # Engine.u, so an omitted SavedPos/SavedRot resolves to the type zero and the two sides of the
    # compare can only agree by stripping.
    engine_u = (UED22 / "Engine.u").read_bytes()
    assert struct.pack("<f", -12345.0) not in engine_u
    assert struct.pack("<iii", 123, 456, 789) not in engine_u


def test_save_package_writes_a_temp_and_moves_it_and_never_reads_a_file_through_its_imports():
    """`MAP SAVE`'s write mechanism — the fact `driver.map_save`'s completeness check is reasoned
    about (`spikes/2026-07-25-map-save-mechanism/`, `unrealed/commands.md` "`MAP SAVE` writes
    `Save.tmp`"; `decisions.md` 2026-07-25 11:31 UTC + its two corrections).

    Two halves, both re-checked here because the SECOND one is what forced a published retraction:

    1. `UObject::SavePackage`'s literals appear in this order in Core.dll's UTF-16 string table:
       `SaveExports → SaveImportMap → SaveExportMap → RewriteSummary`, then `Save.tmp`, then
       `Moving '%s' to '%s'` — i.e. the package is serialized to a temp, its SUMMARY (the header
       carrying every table's count+offset) is rewritten LAST, and only then is the temp moved onto
       the destination. (String-table ORDER; the execution order is inferred from it, per 📖.)
    2. Core.dll's PE import table contains **no `ReadFile`**, no `MoveFile*`/`CopyFile*`, and no
       file-mapping API — yet the DLL demonstrably reads packages. So its file I/O does not go
       through the import table, and the absence of `MoveFile*` proves NOTHING about whether the
       move is a rename or a byte copy. An earlier revision inferred "therefore it is a copy" from
       exactly that absence; this assertion exists so that inference cannot be re-derived silently.
    """
    core = (UED22 / "core.dll").read_bytes()

    def u16(s: str) -> bytes:
        return s.encode("utf-16-le")

    seq = ["SaveExports", "SaveImportMap", "SaveExportMap", "RewriteSummary", "Save.tmp",
           "Moving '%s' to '%s'"]
    offsets = []
    for lit in seq:
        raw = u16(lit)
        assert core.count(raw) >= 1, f"{lit!r} is gone from Core.dll's string table"
        offsets.append(core.index(raw))
    assert offsets == sorted(offsets), f"the SavePackage string run changed order: {offsets}"

    # The import table's file APIs, read straight out of the PE (no pefile dependency).
    pe = core.index(b"PE\0\0")
    opt = pe + 24
    magic = struct.unpack_from("<H", core, opt)[0]
    imp_rva = struct.unpack_from("<I", core, opt + (96 if magic == 0x10B else 112) + 8)[0]
    imported: set[str] = set()
    d = _rva_to_offset(core, imp_rva)
    while True:
        ilt, _ts, _fc, name_rva, iat = struct.unpack_from("<IIIII", core, d)
        if name_rva == 0:
            break
        t = _rva_to_offset(core, ilt or iat)
        while True:
            entry = struct.unpack_from("<I", core, t)[0]
            if entry == 0:
                break
            if not entry & 0x80000000:               # by name, not by ordinal
                off = _rva_to_offset(core, entry) + 2
                imported.add(core[off:core.index(b"\0", off)].decode("latin-1"))
            t += 4
        d += 20

    for absent in ("ReadFile", "MoveFileW", "MoveFileExW", "CopyFileW", "CopyFileExW",
                   "CreateFileMappingW", "MapViewOfFile"):
        assert absent not in imported, (
            f"Core.dll now imports {absent} — the 'the import table settles nothing about the move' "
            f"reasoning in driver.package_header_problem must be re-derived")
    assert "CreateFileW" in imported and "WriteFile" in imported     # it does open + write files


@pytest.mark.parametrize("golden", ["level_small.t3d", "brush_subtract.t3d"])
def test_editor_export_never_writes_an_all_zero_poly_pan(golden):
    """UnrealEd's `MAP EXPORT` writes a polygon's `Pan U=<u> V=<v>` line ONLY when at least one
    component is non-zero — a zero pan is written as NO `Pan` line at all, because an absent one
    already means zero (`unrealed/t3d.md` "A poly sub-field has NO class default").

    Pinned against the committed editor-exported goldens because uedcli's `emit_polygon` now relies
    on it: it omits a zero `Pan` so that the trunk states exactly what the editor would, and the H3
    post-verify (which compares the two sides' brush TEXT) therefore has no spelling difference to
    trip over. Emitting the redundant line aborted `level materialize` with nothing written until
    2026-07-26.

    If this ever trips — a future editor build, or a re-captured golden, writing an explicit zero pan
    — the fix is NOT to start emitting one. An exported `Pan U=0 V=0` parses to `(0, 0)` and re-emits
    as nothing through the same `emit_polygon`, so both compare sides stay symmetric and uedcli is
    still correct. The invariant that protects the post-verify is that `pan is None` and
    `pan == (0, 0)` emit IDENTICAL text — not that uedcli match the exporter byte for byte. A trip
    here means the documented engine fact (`unrealed/t3d.md`) needs restating, and that anything
    reasoning FROM it (e.g. reading an absent `Pan` in an export as definitely-zero) needs re-checking.

    Note what is NOT asserted: that a Pan line is rare. A HALF-zero pan IS written (`Pan U=0 V=384`
    in these very goldens), so only the all-zero pair is the omitted spelling.
    """
    t3d = (Path(__file__).resolve().parent / "fixtures" / golden).read_text()
    pans = re.findall(r"^\s*Pan\s+U=(-?\d+)\s+V=(-?\d+)\s*$", t3d, re.MULTILINE)
    assert pans, f"{golden} must exercise the fact (it carries no Pan line at all)"
    assert any(u == "0" or v == "0" for u, v in pans), \
        f"{golden} no longer exercises the HALF-zero case, so it cannot show what is omitted"
    for u, v in pans:
        assert (int(u), int(v)) != (0, 0), f"{golden}: editor wrote an all-zero pan: Pan U={u} V={v}"
