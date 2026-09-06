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
    `Save.tmp`"; `dev/docs/rationale/driver.md` 2026-07-25 11:31 UTC + its two corrections).

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


# --- texture-side masking (spikes/2026-07-26-texture-masked-property/) --------------------

def _texture_props(pkg, i):
    from uedcli import utexture
    e = pkg.exports[i]
    props, _ = utexture._read_props(pkg.buf, e["soff"], e["soff"] + e["ssize"], pkg.names)
    return props


def test_utexture_bmasked_is_stored_presence_only_and_never_as_false():
    """A UE1 `Texture` records import-time masking as the bool property **`bMasked`**, and UE1 omits
    any property equal to its class default — so `bMasked` present ⇒ masked, absent ⇒ NOT masked, and
    a stored `bMasked=False` never occurs.

    Spike: `dev/docs/spikes/2026-07-26-texture-masked-property/findings.md` §1. Measured over the
    2,669-texture Deus Ex corpus: 191 carry `bMasked`, **all True**.

    **This pin used to run over the two committed `.utx` fixtures alone — 3 textures, none of
    them masked — so it asserted over an empty set and passed vacuously.** It now sweeps the
    git-tracked `uned/UED22` corpus, which carries 317 stored `bMasked` properties across 34
    packages (`conftest.ued22_root()` states the enumeration rule the package count uses). The
    exact 317 is asserted for one reason only: without it the sweep could silently go vacuous
    again — a change that stopped reading the property would leave every assertion below
    unexecuted and the test still green.
    """
    from uedcli import utexture
    from uedcli.tests.conftest import ued22_packages

    fixtures = Path(__file__).parent / "fixtures"
    paths = [fixtures / n for n in ("CoreTexWater.utx", "LUM_InfoPortraits.utx",
                                    "UccCompMips.utx")] + ued22_packages()
    stored = 0
    for path in paths:
        pkg = utexture.load_package(str(path))
        for i in utexture.textures(pkg):
            v = _texture_props(pkg, i).get("bMasked")
            if v is None:
                continue
            stored += 1
            assert v[1] is True, f"{path.name}: bMasked stored as {v!r}"
    assert stored == 317, stored


def test_index_zero_is_an_ordinary_colour_on_an_unmasked_texture():
    """**Palette index 0 is only a cut-out on a masked face** — on any other texture it is an
    ordinary colour that must render opaque.

    `LUM_InfoPortraits.ArthurCallaway` is the committed counter-example: it carries **no** `bMasked`,
    its palette entry 0 is real black `(0,0,0)` (not the reserved magenta key), and **2.2 %** of its
    mip-0 texels use it. A renderer that treats index 0 as transparent unconditionally punches holes
    in this face. Corpus-wide that mistake hits **464 of 2,669** textures, including flat colour
    swatches that are 100 % index 0 and would vanish entirely.

    Spike: `dev/docs/spikes/2026-07-26-texture-masked-property/findings.md` §2-3. This pins the
    gate that `actor diagram --faces textured` depends on.
    """
    from uedcli import utexture
    pkg = utexture.load_package(str(Path(__file__).parent / "fixtures" / "LUM_InfoPortraits.utx"))
    idx = next(i for i in utexture.textures(pkg)
               if pkg.names[pkg.exports[i]["nm"]].casefold() == "arthurcallaway")

    assert "bMasked" not in _texture_props(pkg, idx), "fixture is no longer an UNMASKED texture"

    tex = utexture.decode_texture(pkg, idx)
    # palette_ref is an object REF, not an export index — decode_palette needs the resolved index
    # (passing the raw ref raises "palette body not at EOF"; spike findings.md §4).
    palette = utexture.decode_palette(pkg, utexture.export_index_of_ref(pkg, tex.palette_ref))
    assert palette[0] == (0, 0, 0), f"palette[0] is {palette[0]}, expected real black"

    mip0 = tex.mips[0]
    frac = mip0.data.count(0) / len(mip0.data)
    assert 0.02 < frac < 0.03, f"index-0 usage {frac:.4f} moved; the fixture changed"


# ── LIGHT APPLY lightmap allocation (spike 2026-09-06-lightmap-alloc-zero-vert-gate) ────────────

def test_light_apply_allocates_a_lightmap_only_at_a_node_with_vertices():
    """`LIGHT APPLY`'s world `LightMap` allocation walk, which fixes the array's ORDER.

    `shadowIlluminateBsp` (`Editor.dll` RVA `0xa5e10`) empties `Model->LightMap`, sets every surf's
    `iLightMap` to -1, and then recurses `0x100a4a90` from node 0 (the call at `0x100a60a9`). That
    walk allocates one record per surf, in visit order, gated on

        node->NumVertices != 0  &&  !(surf->PolyFlags & 0x400081)  &&  surf->iLightMap == -1

    then recurses `node+0x24`, `node+0x20`, `node+0x28`. The vertex gate is the load-bearing half:
    a vertex-less node neither allocates nor CLAIMS its surf, so a surf that also sits on a later
    non-empty node is allocated THERE. `uedcli-native`'s `lightmap_emit_order` is that walk; the
    order it produces is the on-disk `LightMap` order and every surf's `iLightMap`.

    The corpus half of the pin (the walk reproduces the stored order of all 161 shipped world
    Models) lives in the spike harness, which needs the gitignored `dev/games/` maps.
    """
    text = (UED22 / "Editor.dll").read_bytes()
    for va, want, what in [
        (0x100A4AD5, "8b7e1c", "mov edi,[esi+0x1c] — node->iSurf"),
        (0x100A4AE1, "807e3600", "cmp byte [esi+0x36], 0 — node->NumVertices"),
        (0x100A4AE7, "f7470481004000", "test [edi+4], 0x400081 — surf->PolyFlags"),
        (0x100A4AF0, "837f18ff", "cmp [edi+0x18], -1 — surf->iLightMap"),
        (0x100A4AFC, "6a286a01", "push 0x28 / push 1 — LightMap.Add(1, sizeof FLightMapIndex)"),
        (0x100A4B10, "8b4624", "mov eax,[esi+0x24] — recurse the 2nd child first"),
        (0x100A4B20, "8b4620", "mov eax,[esi+0x20] — then the 1st"),
        (0x100A4B30, "8b4628", "mov eax,[esi+0x28] — then the iPlane chain"),
    ]:
        off = _rva_to_offset(text, va - _IMAGE_BASE)
        got = text[off:off + len(want) // 2].hex()
        assert got == want, f"Editor.dll {va:#x} ({what}): want {want}, found {got}"


# ── POLY TEXALIGN (spike 2026-07-26-unrealed-texalign-semantics) ────────────────────────────────

_TEXALIGN_SPIKE = (Path(__file__).resolve().parents[2] /
                   "dev" / "docs" / "spikes" / "2026-07-26-unrealed-texalign-semantics")

# Every UED22 DLL is based here; the `push <imm32>` operands in the parser chain are absolute VAs.
_IMAGE_BASE = 0x10000000

# The nine tokens `POLY TEXALIGN` accepts and the ETexAlign value each maps to, in the order the
# exec parser tests them. `unrealed/texalign.md`; `commands.md` used to list only six.
_TEXALIGN_TOKENS = [("DEFAULT", 0), ("FLOOR", 1), ("WALLDIR", 2), ("WALLX", 6), ("WALLY", 7),
                    ("WALLPAN", 3), ("WALLCOLUMN", 5), ("ONETILE", 4), ("CLAMP", 8)]


def _wide_string_at(data: bytes, rva: int) -> str:
    """The NUL-terminated UTF-16LE literal at `rva` (engine `TCHAR` strings are wide)."""
    off = end = _rva_to_offset(data, rva)
    while data[end:end + 2] != b"\0\0":
        end += 2
    return data[off:end].decode("utf-16le")


def test_texalign_parser_maps_nine_tokens_to_these_etexalign_values():
    """`POLY TEXALIGN` accepts NINE mode tokens, not the six `commands.md` used to list — `DEFAULT`,
    `WALLPAN` and `WALLCOLUMN` were missing — and each maps to the ETexAlign value below.

    Spike: `dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/README.md` §1 (all nine driven
    live; the mapping read out of the parser chain at `Editor.dll` RVA 0x68984). Doc:
    `dev/docs/unrealed/texalign.md`.

    The chain is a run of `ParseCommand(&Str, TEXT("<TOKEN>"))` tests, each followed on match by
    `mov dword ptr [ebp-0x4dc], <ETexAlign>` (`C7 85 24 FB FF FF <u32>`). This walks those stores in
    file order and resolves the `push <VA>` immediately before each one back to its wide string, so
    it asserts the token/value PAIRING rather than two independent lists.
    """
    data = (UED22 / "Editor.dll").read_bytes()
    blob = data[_rva_to_offset(data, 0x68984):_rva_to_offset(data, 0x68984) + 0x1A0]
    pairs = []
    for m in re.finditer(rb"\xc7\x85\x24\xfb\xff\xff(....)", blob, re.S):
        value = struct.unpack("<I", m.group(1))[0]
        push = None
        for candidate in re.finditer(rb"\x68(....)", blob[:m.start()], re.S):
            push = candidate                       # the LAST push before the store is the token
        assert push is not None, "no `push <token>` precedes an ETexAlign store"
        va = struct.unpack("<I", push.group(1))[0]
        pairs.append((_wide_string_at(data, va - _IMAGE_BASE), value))
    assert pairs == _TEXALIGN_TOKENS


def test_texalign_onetile_and_wallcolumn_are_unimplemented_in_ued22():
    """`ONETILE` and `WALLCOLUMN` do NOT align anything in this substrate — so UnrealEd 2.2 has no
    fit-a-tile-to-a-face operation at all, and uedcli's proposed `poly align one-tile` is an
    original feature rather than a port of an editor mode.

    Spike: `…/2026-07-26-unrealed-texalign-semantics/README.md` §3.6 (live: the export after
    `POLY TEXALIGN WALLCOLUMN` is byte-identical to the control on all 44 fixture faces, and
    `ONETILE` differs only by sign-of-zero float noise). Doc: `dev/docs/unrealed/texalign.md`.

    Pinned structurally, off `polyTexAlign`'s own jump table (`Editor.dll` RVA 0x4d660, indexed by
    ETexAlign):
      * entry 5 (WALLCOLUMN) is the SAME address as the `default:` branch — the `ja` target of the
        `cmp eax, 8` bounds check — whose body is just `mov ecx,[ebp-0x1f4]; inc ecx; jmp <loop>`;
      * entry 4 (ONETILE) lands on the shared epilogue (`mov [esi+0x18], -1` = invalidate the
        lightmap, then `push 1; push 1` for `polyUpdateMaster`) with no case body of its own.
    """
    data = (UED22 / "Editor.dll").read_bytes()
    # mov eax,[ebp+0xc] ; cmp eax,8 ; ja <default> ; jmp [eax*4 + 0x1004d660]
    dispatch = data[_rva_to_offset(data, 0x4C7C3):_rva_to_offset(data, 0x4C7C3) + 17]
    assert dispatch.startswith(bytes.fromhex("8b450c83f8080f87")), "the ETexAlign dispatch moved"
    assert dispatch.endswith(bytes.fromhex("ff248560d6")), "the jump-table reference moved"
    default_rva = 0x4C7CF + struct.unpack_from("<i", dispatch, 8)[0]

    # The `cmp eax, 8` above is what SIZES the table: indices 0..8, one per accepted token. Read
    # one more entry than that and assert the extra is NOT a code address, so a table that grew
    # (a rebuild adding a mode) trips here rather than being silently mis-indexed below.
    assert len(_TEXALIGN_TOKENS) == 9 and dispatch[4:6] == bytes.fromhex("f808")     # cmp eax, 8
    table = struct.unpack_from("<10I", data, _rva_to_offset(data, 0x4D660))
    rvas = [va - _IMAGE_BASE for va in table[:9]]
    assert table[9] == 0xCCCCCCCC, "the ETexAlign jump table has grown past its 9 entries"

    # WALLCOLUMN == default: nothing happens, not even polyUpdateMaster.
    assert rvas[5] == default_rva
    loop_continue = data[_rva_to_offset(data, rvas[5]):_rva_to_offset(data, rvas[5]) + 8]
    assert loop_continue == bytes.fromhex("8b8d0cfeffff41e9"), \
        "the WALLCOLUMN/default branch is no longer a bare loop-continue"

    # ONETILE == the shared epilogue: invalidate the lightmap, polyUpdateMaster, done.
    assert rvas[4] != default_rva                  # it is not literally the default branch …
    epilogue = data[_rva_to_offset(data, rvas[4]):_rva_to_offset(data, rvas[4]) + 11]
    assert epilogue == bytes.fromhex("c74618ffffffff6a016a01"), \
        "the ONETILE entry no longer lands on the bare polyUpdateMaster epilogue"

    # …and every mode that DOES align has a distinct entry of its own.
    aligning = [rvas[v] for _tok, v in _TEXALIGN_TOKENS if _tok not in ("ONETILE", "WALLCOLUMN")]
    assert len(set(aligning)) == len(aligning)
    assert default_rva not in aligning


def test_texalign_guard_thresholds_are_005_and_095_and_texels_is_ignored():
    """The alignment guards are the two `.rdata` doubles 0.05 and 0.95 — `FLOOR`/`WALLX`/`WALLY`
    skip a face whose `|N[axis]| <= 0.05`, `WALLDIR`/`WALLPAN` skip one whose `|N.Z| >= 0.95` — and
    the `TEXELS=<n>` argument the exec parser accepts is never read by `polyTexAlign` at all.

    Spike: `…/2026-07-26-unrealed-texalign-semantics/README.md` §1 and §3 (live: the guards' skip
    DIRECTION is measured on real faces; the two constants themselves come from `.rdata`, and
    `TEXELS=64` produced identical output on three modes). Doc: `dev/docs/unrealed/texalign.md`.
    """
    data = (UED22 / "Editor.dll").read_bytes()
    body = data[_rva_to_offset(data, 0x4C6C0):_rva_to_offset(data, 0x4D615)]   # polyTexAlign

    for rva, expected, uses in ((0x0DE950, 0.05, 4), (0x0E0578, 0.95, 2)):
        assert struct.unpack_from("<d", data, _rva_to_offset(data, rva))[0] == expected
        assert body.count(struct.pack("<I", _IMAGE_BASE + rva)) == uses, \
            f"polyTexAlign no longer references the {expected} threshold {uses} time(s)"

    # `polyTexAlign(UModel*, ETexAlign, DWORD Texels)`: Model is [ebp+8], the mode is [ebp+0xc],
    # Texels is [ebp+0x10] — and NOTHING in the body reads that slot, in any encoding.
    assert bytes.fromhex("8b450c") in body, "the ETexAlign argument read moved"
    for encoding in ("8b4510", "8b4d10", "8b5510", "8b5d10", "8b7510", "8b7d10",
                     "ff7510", "0fb74510", "8b8510000000"):
        assert bytes.fromhex(encoding) not in body, \
            f"polyTexAlign now reads its Texels argument ({encoding}) — TEXELS= is no longer inert"


def test_texalign_model_reproduces_every_measured_editor_frame():
    """The documented per-mode rules (`dev/docs/unrealed/texalign.md`) reproduce, exactly, what the
    real editor wrote for every face of the spike's fixture in every mode.

    `measured.json` is the committed golden: each face's world geometry from a control export, plus
    the `Origin`/`TextureU`/`TextureV`/`Pan` the editor produced for it under each of the nine
    modes. `texalign_model.frame` is the executable statement of the documented rules, so this trips
    when the rule and the measurement part company — i.e. when the documented formulas are edited
    wrongly, or when a re-capture against a different editor build replaces the golden. It CANNOT
    see a substrate swap on its own (both sides are committed data); the three byte-pattern tests
    above are what watch `uned/UED22/Editor.dll` itself.

    Spike: `dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/` (README §3-4).
    """
    import json
    import sys
    sys.path.insert(0, str(_TEXALIGN_SPIKE))
    try:
        import texalign_model
    finally:
        sys.path.remove(str(_TEXALIGN_SPIKE))

    golden = json.loads((_TEXALIGN_SPIKE / "measured.json").read_text())
    # bound texture -> VSize in texels (only CLAMP reads it)
    vsize = {"ex_bricks": 256, "aircount_a00": 64, "calendar_2": 256}
    # bspAddVector(…, Exact=0) shares near-equal vectors between surfaces; bspAddPoint plus the
    # float32 world<->brush-local round trip moves an anchor by well under a tenth of a uu.
    vec_tol, point_tol = 2e-3, 0.2

    checked = 0
    for mode, faces in golden["modes"].items():
        for ref, got in faces.items():
            face = golden["faces"][ref]
            pred = texalign_model.frame(
                mode, face["n_surf"], face["n_poly"], face["verts"],
                face["base"], face["tu"], face["tv"], face["pan"], vsize[face["tex"]])
            if pred is None:                        # the mode leaves this face alone
                pred = (face["base"], face["tu"], face["tv"], face["pan"])
            for name, want, have, tol in (("Origin", pred[0], got["base"], point_tol),
                                          ("TextureU", pred[1], got["tu"], vec_tol),
                                          ("TextureV", pred[2], got["tv"], vec_tol)):
                assert all(abs(a - b) <= tol for a, b in zip(want, have)), \
                    f"{mode} {ref}: {name} predicted {want}, editor wrote {have}"
            assert list(pred[3]) == list(got["pan"]), f"{mode} {ref}: Pan"
            checked += 1
    assert checked == 396, f"the golden covers {checked} (mode, face) pairs, expected 396"


def test_texalign_guards_match_the_editor_on_near_threshold_faces():
    """The guard thresholds in the documented rule are the ones the real editor applies, checked
    where it matters — on faces whose normals straddle them by 0.001.

    `measured.json`'s fixture has no near-threshold face, so the model check above would pass with a
    badly-wrong threshold. `guards.json` closes that: eight one-wedge levels, each exported with and
    without the mode whose guard its test face straddles, recording only whether the editor TOUCHED
    that face. Measured live 2026-07-26 — `|N[axis]|` 0.049 vs 0.051 for `FLOOR`/`WALLX`/`WALLY`,
    `|N.Z|` 0.949 vs 0.951 for `WALLDIR` — so each threshold is pinned to a 0.002-wide window.

    Spike: `dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/README.md` §5.1.
    """
    import json
    import sys
    sys.path.insert(0, str(_TEXALIGN_SPIKE))
    try:
        import texalign_model
    finally:
        sys.path.remove(str(_TEXALIGN_SPIKE))

    cases = json.loads((_TEXALIGN_SPIKE / "guards.json").read_text())["cases"]
    assert len(cases) == 8
    assert {c["changed"] for c in cases} == {True, False}       # the golden brackets, not one side
    for case in cases:
        n = case["n_surf"]
        # Anything but the guard is irrelevant here: pass a placeholder frame/geometry and ask only
        # whether the model decides to act.
        acted = texalign_model.frame(case["mode"], n, n, [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                                     (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
                                     (0, 0), 256) is not None
        assert acted == case["changed"], (
            f"{case['case']}: TEXALIGN {case['mode']} on normal {n} — the editor "
            f"{'changed' if case['changed'] else 'left'} the face, the documented rule says "
            f"{'act' if acted else 'skip'}")


def test_texalign_pan_handling_matches_the_editor_against_a_non_zero_pan():
    """Which modes ZERO a surface's `Pan` and which leave it alone — measured where it is visible.

    The main fixture cannot show this: all 44 of its faces already carried `Pan = (0,0)`, so
    "the mode sets the pan to zero" and "the mode never touches the pan" produce identical exports,
    and `measured.json` therefore cannot discriminate. `pans.json` is a re-run of the same fixture
    with **`Pan U=7 V=13` authored on every face**, which separates them: `WALLCOLUMN`/`ONETILE`/
    `WALLPAN` came back `(7,13)` on all 44, `DEFAULT` came back `(0,0)` on all 44, the guarded modes
    zeroed exactly the faces their guard admits, and `CLAMP` came back `(0, VSize−1)` — `(0,63)` on
    the eleven faces textured `AirCount_A00` and `(0,255)` on the rest.

    That last split re-confirms `CLAMP`'s `VSize` dependence on a second, independent run, and the
    guarded splits re-confirm the guards from a signal entirely different from the frame geometry.

    Spike: `dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/README.md` §5.3.
    """
    import json
    import sys
    sys.path.insert(0, str(_TEXALIGN_SPIKE))
    try:
        import texalign_model
    finally:
        sys.path.remove(str(_TEXALIGN_SPIKE))

    golden = json.loads((_TEXALIGN_SPIKE / "pans.json").read_text())
    authored = tuple(golden["authored_pan"])
    assert authored != (0, 0), "the golden must carry a NON-ZERO authored pan or it proves nothing"
    vsize = {"ex_bricks": 256, "aircount_a00": 64, "calendar_2": 256}

    checked = 0
    seen = set()
    for mode, faces in golden["pans"].items():
        for ref, got in faces.items():
            face = golden["faces"][ref]
            pred = texalign_model.frame(
                mode, face["n_surf"], face["n_poly"], face["verts"],
                face["base"], face["tu"], face["tv"], authored, vsize[face["tex"]])
            want = list(authored) if pred is None else [int(pred[3][0]), int(pred[3][1])]
            assert want == got, f"{mode} {ref}: pan predicted {want}, editor wrote {got}"
            seen.add(tuple(got))
            checked += 1
    assert checked == 396, f"the golden covers {checked} (mode, face) pairs, expected 396"
    # the golden must actually EXERCISE both outcomes, or a "never touches the pan" model passes
    assert authored in seen and (0, 0) in seen and (0, 63) in seen and (0, 255) in seen


# --- `brush poly align wall|floor` reproduces the editor's projection family (§4.2 parity pins) ---
# These assert uedcli's OWN implementation (`polyalign.align`) against the same editor golden, not the
# reference model — the cheapest thing that catches a dropped negation, a swapped axis or a wrong
# derived axis. A face square to its projection axis is unit; a tilted one carries the |proj| stretch.

def _align_world_frame(verts, mode):
    """Run `brush poly align <mode>` on a unrotated brush at the origin whose one poly has exactly
    `verts` (there the stored frame IS the world frame) and return `(origin, tu, tv, pan)`."""
    from uedcli import polyalign
    from uedcli.builders import make_brush_actor
    from uedcli.model import Brush, Level, Polygon
    a = make_brush_actor("F", Brush("Model", [Polygon(vertices=[tuple(v) for v in verts])]))
    lv = Level()
    lv.actors[a.name] = a
    lv.order = [a.name]
    polyalign.align(lv, ["F:0"], mode)
    p = a.brush.polys[0]
    return p.origin, p.texture_u, p.texture_v, p.pan


def _assert_editor_frame(label, got, want, point_tol=0.2, vec_tol=2e-3):
    for name, g, w, tol in (("Origin", got[0], want["base"], point_tol),
                            ("TextureU", got[1], want["tu"], vec_tol),
                            ("TextureV", got[2], want["tv"], vec_tol)):
        assert all(abs(x - y) <= tol for x, y in zip(g, w)), \
            f"{label}: {name} got {g}, editor wrote {w}"
    assert list(got[3]) == list(want["pan"]), f"{label}: Pan got {got[3]}, editor wrote {want['pan']}"


def test_align_floor_reproduces_editor_FLOOR_on_every_guarded_face():
    """`brush poly align floor` writes the exact frame `POLY TEXALIGN FLOOR` produced, on every
    measured face passing the |N.Z| > 0.05 guard — including the |proj| density stretch on tilted
    faces (the 45° ramp stores |TextureU| = 0.70711). Spike 2026-07-26-unrealed-texalign-semantics."""
    import json
    golden = json.loads((_TEXALIGN_SPIKE / "measured.json").read_text())
    checked = 0
    for ref, face in golden["faces"].items():
        if abs(face["n_surf"][2]) <= 0.05:                  # floor exits 2 here; editor leaves it
            continue
        got = _align_world_frame(face["verts"], "floor")
        _assert_editor_frame(f"FLOOR {ref}", got, golden["modes"]["FLOOR"][ref])
        checked += 1
    assert checked >= 15, f"only {checked} floor faces checked"


def test_align_wall_reproduces_editor_WALLX_WALLY_and_pins_the_derived_axis():
    """`brush poly align wall` derives its projection axis (|N.X| ≥ |N.Y| ⇒ X else Y) and reproduces
    the corresponding editor mode. A wrong derivation picks the wrong golden and fails. Faces failing
    the derived-axis guard are skipped — the editor leaves them untouched, so comparing exit 2 to an
    untouched golden would fail a correct implementation (§4.2)."""
    import json
    golden = json.loads((_TEXALIGN_SPIKE / "measured.json").read_text())
    checked = 0
    for ref, face in golden["faces"].items():
        n = face["n_surf"]
        axis = 0 if abs(n[0]) >= abs(n[1]) else 1           # wall's own derivation
        if abs(n[axis]) <= 0.05:
            continue
        want = golden["modes"]["WALLX" if axis == 0 else "WALLY"][ref]
        got = _align_world_frame(face["verts"], "wall")
        _assert_editor_frame(f"wall(A={'XY'[axis]}) {ref}", got, want)
        checked += 1
    assert checked >= 10, f"only {checked} wall faces checked"


def test_align_wall_tie_break_picks_x_on_a_measured_corner():
    """The |N.X| == |N.Y| tie resolves to X — pinned on SlantXYZ:3, a MEASURED corner normal
    (0.577, 0.577, 0.577) whose WALLX and WALLY goldens differ, so a tie resolved the wrong way
    would pick WALLY and fail (§4.2)."""
    import json
    golden = json.loads((_TEXALIGN_SPIKE / "measured.json").read_text())
    face = golden["faces"]["SlantXYZ:3"]
    assert abs(face["n_surf"][0]) == abs(face["n_surf"][1])         # a genuine tie
    assert golden["modes"]["WALLX"]["SlantXYZ:3"]["tu"] != golden["modes"]["WALLY"]["SlantXYZ:3"]["tu"]
    got = _align_world_frame(face["verts"], "wall")
    _assert_editor_frame("wall tie SlantXYZ:3", got, golden["modes"]["WALLX"]["SlantXYZ:3"])


def test_align_floor_is_invariant_under_normal_reversal():
    """Feeding the reversed winding (the subtractive-brush case, normal negated) yields a
    byte-identical frame — the invariance that licenses uedcli's brush-polygon normal where the
    editor uses the CSG surface normal (§2.3, §4.2)."""
    import json
    golden = json.loads((_TEXALIGN_SPIKE / "measured.json").read_text())
    ref = next(r for r, f in golden["faces"].items() if abs(f["n_surf"][2]) > 0.5)   # a floor/ceiling
    verts = golden["faces"][ref]["verts"]
    forward = _align_world_frame(verts, "floor")
    reversed_ = _align_world_frame(list(reversed(verts)), "floor")
    assert forward == reversed_, f"{ref}: floor frame changed under normal reversal"


# --- UCC-built texture fixture (spikes/2026-07-26-ucc-texture-fixture/) -------------------

_UCC_FIXTURE = (Path(__file__).resolve().parents[2] / "dev" / "docs" / "spikes"
                / "2026-07-26-ucc-texture-fixture" / "fixture")


def test_ucc_builds_a_p8_mip_chain_that_decodes_byte_exactly():
    """`ucc make` + `#exec TEXTURE IMPORT … MIPS=ON` builds the WHOLE mip chain itself, and
    uedcli's P8 decode of it is **byte-exact** against the source artwork that was imported.

    This is the offline fixture's whole justification: the pixel bytes are written by the game's
    own toolchain from artwork we authored, so a decode oracle built on it is independent of
    uedcli without shipping any copyrighted content. Spike:
    `dev/docs/spikes/2026-07-26-ucc-texture-fixture/findings.md` §1.

    If this ever goes non-zero, either the decoder drifted or the committed fixture was rebuilt
    with a different importer — both are things a later change must not do silently.
    """
    from uedcli import utexture
    pytest.importorskip("PIL")
    from PIL import Image

    pkg = utexture.load_package(str(_UCC_FIXTURE / "UccFix.u"))
    idxs = utexture.textures(pkg)
    assert len(idxs) == 1
    tex = utexture.decode_texture(pkg, idxs[0])

    # UCC built the chain, not us: 64x64 down to 1x1, halving.
    assert [(m.width, m.height) for m in tex.mips] == [
        (64, 64), (32, 32), (16, 16), (8, 8), (4, 4), (2, 2), (1, 1)]
    assert tex.fmt == 0, "fixture is no longer P8"

    palette = utexture.decode_palette(
        pkg, utexture.export_index_of_ref(pkg, tex.palette_ref))
    assert len(palette) == 256

    mip0 = tex.mips[0]
    assert len(mip0.data) == mip0.width * mip0.height
    decoded = Image.frombytes(
        "RGB", (mip0.width, mip0.height), utexture.mip0_to_rgb(mip0, palette))
    source = Image.open(_UCC_FIXTURE / "fixture.pcx").convert("RGB")
    assert list(decoded.getdata()) == list(source.getdata()), \
        "UCC's P8 mip 0 no longer decodes byte-exactly to the imported artwork"


# ---------------------------------------------------------------- how brushes enter the level
# Spike `dev/docs/spikes/2026-07-26-map-import-brush-bounds/` (live 2026-07-26), extending the
# 2026-06-28 finding in `dev/docs/unrealed/quirks.md` "How brushes enter the level".

_BOUNDS = Path(__file__).resolve().parent / "fixtures" / "map_import_bounds"


def _world_model_counts(dx: Path) -> tuple[int, int]:
    """(nodes, surfs) of the built world model in a saved map — the offline tell for whether a
    brush actually participated in CSG."""
    from uedcli.native.pkg_write import parse_package
    from uedcli.native.umodel import parse_model_body
    raw = dx.read_bytes()
    p = parse_package(raw)
    models = [(i, e) for i, e in enumerate(p.exports) if p.class_of_export(i) == "Model"]
    assert models, f"{dx.name} holds no Model export at all"
    _, e = max(models, key=lambda t: t[1]["ssize"])
    m = parse_model_body(raw, e["soff"], e["ssize"])
    return len(m.nodes), len(m.surfs)


@pytest.mark.parametrize("golden,expect_csg", [
    ("paste.dx", True),        # EDIT PASTE — the production path
    ("importadd.dx", False),   # MAP IMPORTADD — the 2026-06-28 known-bad control
    ("import.dx", False),      # MAP IMPORT   — the whole-level REPLACE form, probed 2026-07-26
])
def test_only_edit_paste_gets_a_brush_into_csg(golden, expect_csg):
    """A brush that enters the level by importing T3D never participates in CSG — under EITHER
    import form — while `EDIT PASTE` does.

    Why this is pinned. `ULevelFactory` (which serves both `MAP IMPORT` and `MAP IMPORTADD`) does
    not compute a brush's `Bound`, and `MAP REBUILD` does not compute it later either, so CSG skips
    the brush entirely and the built world model comes out with ZERO nodes. The map still saves,
    still parses, and still draws its wireframe in the editor — but its world is solid, so the real
    game dies at `Failed to spawn player actor`. That makes this failure silent in every check
    except a node count, which is why it is worth a standing test.

    The three goldens are real `MAP SAVE` output from one editor session driven three ways over the
    SAME two-brush fixture (a subtractive room plus an additive pillar), so they differ only in the
    verb that introduced the brushes. If a future editor build ever makes an imported brush
    CSG-capable, `import.dx`/`importadd.dx` stop being reproducible and this test must be re-run
    live (`harness/probe.py` in the spike dir) rather than edited to match.
    """
    nodes, surfs = _world_model_counts(_BOUNDS / golden)
    if expect_csg:
        assert nodes > 0 and surfs > 0, (
            f"{golden}: EDIT PASTE no longer yields a CSG-participating brush "
            f"(nodes={nodes}, surfs={surfs}) — the materialize drive rests on this")
    else:
        assert nodes == 0 and surfs == 0, (
            f"{golden}: an IMPORTED brush now participates in CSG (nodes={nodes}, surfs={surfs}). "
            f"That would be GOOD news — re-run the spike probe and revisit the drive design, "
            f"which uses EDIT PASTE only because this was impossible")
