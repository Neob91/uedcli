"""Real stock UnrealScript packages compiled byte-exact vs UCC, via `gate.perm_gate`.

These are the first entries of the byte-parity corpus: pure-script brush-builder packages from
`uned/UED22` (no `native noexport`), so their UCC-decompiled sources recompile under UCC. Each
fixture is `fixtures/uscript/realpkg/<Pkg>/`: the decompiled `.uc` sources plus `<Pkg>.u`, a FRESH
`UCC make` of exactly those sources (the reference — NOT the shipped package, whose class default
block is editor-serialized and drops own zero-valued props).

Two checks per package:
  1. OFFLINE (no docker): `perm_gate(compile_package_dir(sources), committed_golden)` is byte-exact
     modulo the documented exclusions (GUID + name/import/export table ORDER + FName CASE).
  2. DOCKER-GATED: rebuild the golden with UCC from the committed sources and re-gate, catching any
     drift between the committed golden and today's UCC.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import gate, perm_gate
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript" / "realpkg"
_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

# (package, class count) — pins the export identity coverage per package.
_PACKAGES = [("FrameBuilder", 1), ("RahnemBrushBuilders", 1), ("ExtendedBuilders", 2),
             ("DavesBrushBuilders", 1), ("UnrealShare", 1)]


def _sources(pkg: str) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted((_FIX / pkg).glob("*.uc"))}


def _compile(pkg: str) -> bytes:
    return serialize(compile_package_dir(_sources(pkg), InstallEnv([str(_UED22)]), package_name=pkg))


def _class_count(u: bytes) -> int:
    import tempfile, os
    from uedcli.upackage import load_package
    fd, p = tempfile.mkstemp(suffix=".u", dir=os.environ.get("TMPDIR")); os.close(fd)
    try:
        Path(p).write_bytes(u)
        pk = load_package(p)
        return sum(1 for e in pk.exports if e["cls"] == 0)
    finally:
        os.unlink(p)


@pytest.mark.parametrize("pkg,classes", _PACKAGES)
def test_realpkg_offline_byte_exact(pkg: str, classes: int):
    """Autonomous compile of the committed sources passes `perm_gate` against the committed UCC
    golden, and carries the expected class count."""
    mine = _compile(pkg)
    assert _class_count(mine) == classes
    r = perm_gate(mine, (_FIX / pkg / f"{pkg}.u").read_bytes())
    assert r.passed, f"{pkg}: " + " | ".join(r.messages)


@pytest.mark.parametrize("pkg", ["FrameBuilder", "RahnemBrushBuilders", "UnrealShare"])
def test_realpkg_strict_byte_exact(pkg: str):
    """These two also pass the STRICT gate (name/import/export table ORDER included, not just
    content) with no `order_override` — `RahnemBrushBuilders` pins the value-only-name gather-order
    fix (a package self-name in `PackageImports` registers at class-header time; a defaultproperties
    tag VALUE registers after every member/function, per `ordering._gather_names`/`late_name_refs`).
    `ExtendedBuilders` still fails on raw byte count (a qsort-tie permutation among a larger group of
    real-pool + own-new names, not isolated); `DavesBrushBuilders` now diverges only on ONE isolated
    pair (see `test_davesbrushbuilders_ast_order_recovers_enum_property_interleaving`) — both open,
    not this fix."""
    r = gate(_compile(pkg), (_FIX / pkg / f"{pkg}.u").read_bytes())
    assert r.passed, f"{pkg}: " + " | ".join(r.messages)


def test_davesbrushbuilders_name_table_byte_exact():
    """RE'd 2026-09-13 (`findings-ordering-re.md`): two fixes to `reorder`/`ordering`'s name
    registration model. (1) UCC's name-registration order follows TRUE SOURCE-TEXTUAL order (a
    property and a later `var() enum` register side by side, exactly as declared), but the compiled
    `.u`'s own Children chain bins ALL properties into one forward sub-chain and ALL non-properties
    (enums/consts/structs/functions) into a separate reverse sub-chain, losing that interleaving
    structurally. `compile._top_level_name_order` recovers it from the parsed AST (`ClassDecl.
    decl_order`, before that binning happens) and threads it through `reorder.true_order`'s
    `class_order`/`top_level_by_class` params. This alone left one pair swapped: `Core` (a real
    engine pool name) and `DavesBrushBuilders` (the package's own self-name), both reference-count 1.

    (2) A live `AllocateNameEntry` capture of a real `UCC.exe make` of this same package (also in
    `findings-ordering-re.md`) showed the package's own PackageImports[0] self-reference registers
    BEFORE the class's own FName, not after — the earlier "registers at class-header time" model
    only pinned the self-name ahead of the class's first member, not ahead of the class's own name
    too. `ordering._gather_names` now special-cases a `Class`-kind object's `name_refs[1]`
    (PackageImports[0], always the self-reference per `compile-model.md`) to register before
    `add(o.disp)`. This closes the Core/self-name swap: the name table is now byte-exact.

    `DavesBrushBuilders` still fails the STRICT gate (see `test_realpkg_strict_byte_exact`'s
    parametrize list, which does not include it) on an UNRELATED, newly-found export-table
    qsort-tie-permutation among four tied-refcount local/param objects across different functions —
    tracked at `dev/docs/board/inbox/davesbrushbuilders-export-table-qsort-tie/`."""
    from uedcli.upackage import _parse_package

    mine = _compile("DavesBrushBuilders")
    golden = (_FIX / "DavesBrushBuilders" / "DavesBrushBuilders.u").read_bytes()
    mn = list(_parse_package(mine, "<mine>", "mine").names)
    gn = list(_parse_package(golden, "<golden>", "golden").names)
    assert mn == gn


def test_davesbrushbuilders_locals_register_inline_not_deferred():
    """Pins a live `AllocateNameEntry` capture (`core.dll` VA `0x1005cdc0`, a real `UCC.exe make` of
    this committed golden under `winedbg`; see `findings-ordering-re.md` 2026-09-13): a function's
    body LOCALS register immediately after that function, not deferred to a trailing pass over every
    function. The capture showed `im` (an `Extrapolate3` local) between `Extrapolate3` and the next
    function `Extrapolate4`, and `dR` (a `BuildCube` local) between `Extrapolate5` and
    `BuildOctahedron` (`BuildCube`'s own name is a pre-existing import, so `BuildCube` itself never
    appears in the own-new name stream, but its local's position still splits `Extrapolate5` from
    `BuildOctahedron`). This does not by itself make `DavesBrushBuilders` gate byte-exact (a separate,
    open bug in enum-vs-property interleaving still diverges the table earlier) but is independently
    checkable from `reorder.name_creation_order`'s own output."""
    from uedcli.uscript.reorder import _Decoder

    u = (_FIX / "DavesBrushBuilders" / "DavesBrushBuilders.u").read_bytes()
    d = _Decoder(u)
    exp_i = {d.ekey(i): i for i in range(len(d.p.exports))}
    disp = [d.edisp(exp_i[k]) for k in d.name_creation_order()]

    def idx(name: str) -> int:
        return disp.index(name)

    assert idx("Extrapolate3") < idx("im") < idx("Extrapolate4")
    assert idx("Extrapolate5") < idx("dR") < idx("BuildOctahedron")


# ── docker-gated fresh rebuild ────────────────────────────────────────────────────────────────────
def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@pytest.mark.integration
@pytest.mark.skipif(not (_docker_up() and (_UED22 / "UCC.exe").is_file()),
                    reason="needs a live docker daemon and the committed UED22 substrate (UCC.exe)")
@pytest.mark.parametrize("pkg,classes", _PACKAGES)
def test_realpkg_matches_fresh_ucc(pkg: str, classes: int, tmp_path):
    """A fresh `UCC make` of the committed sources still matches our compile — guards against golden
    drift from today's toolchain."""
    from uedcli.uscript.reference import ucc_compile, ucc_container
    sources = _sources(pkg)
    with ucc_container(state_dir=tmp_path) as container:
        fresh = ucc_compile(container, pkg, sources)
    r = perm_gate(_compile(pkg), fresh)
    assert r.passed, f"{pkg} vs fresh UCC: " + " | ".join(r.messages)
