"""Assemble `uedcli/tests/fixtures/UccCompMips.utx` — the two-mip-array texture fixture.

**Run by hand; its output is COMMITTED.** No test rebuilds the fixture to check its PIXELS —
that would test our own writer against our own reader, the exact circularity the fixture's design
exists to avoid. One test does check that `build()` still reproduces the committed BYTES, which is
a different thing: a reproducibility pin, not a decode oracle. Without it the two drift silently —
they already did once, when a new property name lengthened the package's name table and shifted
every absolute mip offset.

    .venv/bin/python -m uedcli.tests.build_uccfixture      # from the repo root

What the fixture is, and why its provenance matters. The decoder's BC1 (DXT1) output is checked
against a P8 copy of the *same picture* stored in the same package. That is evidence only if
something other than uedcli encoded both copies. So:

  * the artwork is OURS — generated deterministically, no game content;
  * the **P8 mip chain was built by the game's own `ucc make`** (`#exec TEXTURE IMPORT …
    MIPS=ON`), which builds the whole 7-level pyramid itself;
  * the **DXT1 blocks were written by Pillow 12.3.0** (`format="DDS", pixel_format="DXT1"`) —
    third party to uedcli, and already the repo's only runtime dependency. UCC cannot produce
    them: this toolchain has no DDS importer.
  * only the CONTAINER is ours, assembled below by `pkgfixture`.

Both inputs are committed spike output under
`dev/docs/spikes/2026-07-26-ucc-texture-fixture/fixture/`, so this script needs no wine, no game
install and no network. Evidence and the measured numbers: that spike's `findings.md`.
"""
from __future__ import annotations

import struct
from pathlib import Path

from uedcli import utexture
from uedcli.tests import pkgfixture

_REPO = Path(__file__).resolve().parents[2]
_SPIKE = _REPO / "dev" / "docs" / "spikes" / "2026-07-26-ucc-texture-fixture" / "fixture"
_OUT = Path(__file__).resolve().parent / "fixtures" / "UccCompMips.utx"

TEXTURE_NAME = "SpikeFixture"
_DDS_HEADER_BYTES = 128


def _p8_from_ucc() -> tuple[list[tuple[int, int, bytes]], list[tuple[int, int, int, int]]]:
    """UCC's own P8 mip chain + palette, out of the committed `UccFix.u`."""
    pkg = utexture.load_package(str(_SPIKE / "UccFix.u"))
    i = utexture.textures(pkg)[0]
    tex = utexture.decode_texture(pkg, i)
    pal = utexture.decode_palette(pkg, utexture.export_index_of_ref(pkg, tex.palette_ref))
    mips = [(m.width, m.height, m.data) for m in tex.mips]
    return mips, [(r, g, b, 255) for (r, g, b) in pal]


def _dxt1_from_dds(dims: list[tuple[int, int]]) -> list[tuple[int, int, bytes]]:
    """Pillow's DXT1 pyramid, split out of the committed `fixture.dds`.

    The file is a single DDS with `dwMipMapCount = len(dims)` and the levels concatenated after
    the 128-byte header. DXT1 stores `ceil(w/4)·ceil(h/4)` eight-byte blocks per level, so each
    level's length is computable from its dimensions — which is also the check that the .dds
    and the .u describe the same pyramid.
    """
    raw = (_SPIKE / "fixture.dds").read_bytes()
    if raw[:4] != b"DDS ":
        raise SystemExit(f"{_SPIKE/'fixture.dds'}: not a DDS file")
    declared = struct.unpack_from("<I", raw, 28)[0]
    if declared != len(dims):
        raise SystemExit(f"fixture.dds has {declared} levels, UccFix.u has {len(dims)}")
    out, pos = [], _DDS_HEADER_BYTES
    for (w, h) in dims:
        n = ((w + 3) // 4) * ((h + 3) // 4) * 8
        out.append((w, h, raw[pos:pos + n]))
        pos += n
    if pos != len(raw):
        raise SystemExit(f"fixture.dds: {len(raw) - pos} bytes past the last DXT1 level")
    return out


def build() -> bytes:
    """The assembled `.utx` bytes: one `Engine.Palette` + one `Engine.Texture` export whose
    `Mips` is UCC's P8 chain and whose `CompMips` is Pillow's DXT1 chain (`CompFormat = 3`)."""
    mips, palette = _p8_from_ucc()
    comp = _dxt1_from_dds([(w, h) for (w, h, _) in mips])
    return pkgfixture.texture_package(name=TEXTURE_NAME, mips=mips, palette=palette,
                                      comp_mips=comp, comp_format=3)


def main() -> int:
    buf = build()
    _OUT.write_bytes(buf)
    print(f"wrote {_OUT} — {len(buf)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
