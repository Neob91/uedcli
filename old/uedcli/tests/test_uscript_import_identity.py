"""Import IDENTITY collision: two imports sharing a bare display name.

Found compiling the real UT99 `IpServer` package (`USCRIPT-COMPILER.md`,
`dev/docs/board/inbox/uscript-cross-package-import-identity-collides/`): `GameInfo`'s own member
field `GameReplicationInfo` is named identically to its TYPE, the class `Engine.GameReplicationInfo`
-- two distinct import rows (a Class and an ObjectProperty) that used to collide onto one `b.imports`
key via `compile._imports_by_display`'s bare-name lookup, dropping one row and raising `KeyError`.

Fixed by giving every import a disambiguated internal identity end to end: `reorder._Decoder` keys
each import row by its own table INDEX (`ikey`, mirroring the export `ekey`) instead of its display
spelling, so two same-named import rows stay distinct through `ordering.order_package`'s refcount
tally and gather; `reorder.true_order` returns import rows as (display, outer display) pairs, the
same disambiguation `export_rows` already carried; `compile._imports_by_display` maps a row back to
its `b.imports` key by (display, outer) when the bare display alone is ambiguous.

This fixture's CONTENT is byte-exact (`perm_gate`, the identity/permutation bar): the import table
carries both rows and every reference resolves correctly. The strict `gate()` fails on an unrelated,
already-tracked gap -- the import/name table ORDER tie-break among stock objects that share a
reference count (the same open `qsort`-tie-permutation class as `ExtendedBuilders`,
`dev/docs/board/inbox/extendedbuilders-name-table-qsort-residual/`), not anything this fix touches.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import perm_gate
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript"
_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"
_PKG = "UscImportIdentityProbe"
_SRC = (_FIX / f"{_PKG}.uc").read_text()


def _compile() -> bytes:
    return serialize(compile_package_dir({f"{_PKG}.uc": _SRC}, InstallEnv([str(_UED22)]),
                                         package_name=_PKG))


def test_import_identity_collision_offline_byte_exact():
    """Autonomous compile (no `order_override`) matches the committed UCC golden at `perm_gate`: the
    class import `GameReplicationInfo` and the field import `GameInfo.GameReplicationInfo` both land
    as distinct rows, and every reference (`Level.Game.GameReplicationInfo.Region`) resolves to the
    right one."""
    r = perm_gate(_compile(), (_FIX / f"{_PKG}.u").read_bytes())
    assert r.passed, " | ".join(r.messages)


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
def test_import_identity_collision_matches_fresh_ucc(tmp_path):
    from uedcli.uscript.reference import ucc_compile, ucc_container
    with ucc_container(state_dir=tmp_path) as c:
        fresh = ucc_compile(c, _PKG, {f"{_PKG}.uc": _SRC})
    r = perm_gate(_compile(), fresh)
    assert r.passed, " | ".join(r.messages)
