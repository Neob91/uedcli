"""Recover UnrealEd's ortho-viewport grid density rule from `Editor.dll`.

Static only — reads the file, never runs the editor (`dev/docs/unrealed/extracting-from-dll.md`).

Locates `UEditorEngine::DrawGridSection` via the export table, disassembles it, and asserts the
facts the spike claims: the power-of-two escalation loop, the density threshold, the two alpha
tiers, the every-8th-line major rule, the world clamp, the colour lerp and the parity split. Run it
to re-verify:

    python3 grid_density.py ../../../../uned/UED22/Editor.dll
"""

import struct
import sys

import capstone
import pefile

EXPORT = b"?DrawGridSection@UEditorEngine@@UAEXPAUFSceneNode@@HHHPAVFVector@@1PAM2H@Z"


def find_export(pe: pefile.PE, name: bytes) -> int:
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    for sym in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if sym.name == name:
            return sym.address
    raise SystemExit(f"export not found: {name.decode()}")


def disasm(pe: pefile.PE, rva: int, length: int = 0x900) -> list:
    img = pe.get_memory_mapped_image()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return list(md.disasm(img[rva:rva + length], pe.OPTIONAL_HEADER.ImageBase + rva))


def f32(pe: pefile.PE, va: int) -> float:
    rva = va - pe.OPTIONAL_HEADER.ImageBase
    return struct.unpack("<f", pe.get_memory_mapped_image()[rva:rva + 4])[0]


def main(path: str) -> None:
    pe = pefile.PE(path, fast_load=True)
    rva = find_export(pe, EXPORT)
    ins = disasm(pe, rva)
    text = [f"{i.mnemonic} {i.op_str}".strip() for i in ins]
    checks: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append((label, bool(ok), detail))

    # 9 stdcall args (FSceneNode*, 3 ints, 2 FVector*, 2 float*, int) -> callee pops 0x24.
    check("signature: 9 args, `ret 0x24`", "ret 0x24" in text)

    # `if (!ViewportGridY) return;` — 4th arg at [ebp+0x14].
    check("early-out on GridY == 0",
          any(t == "mov edi, dword ptr [ebp + 0x14]" for t in text)
          and "test edi, edi" in text)

    # The escalation loop: shift++ while (count >> shift) >= threshold.
    i_shift = next((k for k, t in enumerate(text) if t == "sar edx, cl"), None)
    check("escalation loop present (`sar edx, cl` / `cmp edx, eax` / `inc esi`)",
          i_shift is not None
          and text[i_shift + 1] == "cmp edx, eax"
          and "inc esi" in text[i_shift:i_shift + 5])

    # Threshold is viewport-width / 4 (signed div-by-4 idiom: cdq / and edx,3 / add / sar 2).
    j = next((k for k, t in enumerate(text) if t == "and edx, 3"), None)
    check("threshold = width / 4 (signed div-by-4 idiom)",
          j is not None and text[j + 1].startswith("add eax") and text[j + 2] == "sar eax, 2")

    # The drawn step is GridY << shift, and the loop bounds are shifted down by the same amount.
    check("step scaled by 1 << shift", "shl eax, cl" in text and "sar edi, cl" in text)

    # World clamp: the grid spans -32768 .. +32768 world units, divided by GridY.
    check("world clamp -32768", "mov eax, 0xffff8000" in text)
    check("world clamp +32768", "mov eax, 0x8000" in text)

    # Two alpha tiers, selected by (index << shift) & 7.
    k = next((n for n, t in enumerate(text) if t == "test al, 7"), None)
    check("major/minor selected by `& 7` (every 8th line)", k is not None)

    alphas = []
    if k is not None:
        for t in text[k:k + 8]:
            if t.startswith("movss xmm0, dword ptr [0x"):
                alphas.append(int(t.split("[")[1].rstrip("]"), 16))
    vals = [f32(pe, a) for a in alphas]
    check("alpha tiers are 0.5 (minor) and 1.0 (major)",
          sorted(vals) == [0.5, 1.0], f"read {vals}")

    # The lerp target: FPlane(0.5, 0.5, 0.5, 0.0) loaded with movaps just before the tier select.
    grey = struct.unpack("<4f", pe.get_memory_mapped_image()[0xe6930:0xe6940])
    check("lerp target GREY == (0.5, 0.5, 0.5, 0.0)", grey == (0.5, 0.5, 0.5, 0.0), f"read {grey}")

    # The fade numerator, used as `2.0 - (2*count)/((1<<shift)*limit)`.
    check("fade numerator == 2.0", f32(pe, 0x100d2f84) == 2.0)

    # Parity: the line is skipped when (i & 1) == AlphaCase (arg 9, [ebp+0x28]).
    m = next((n for n, t2 in enumerate(text) if t2 == "and eax, 1"), None)
    check("parity skip on `(i & 1) == AlphaCase`",
          m is not None and any(t2 == "cmp eax, dword ptr [ebp + 0x28]" for t2 in text[m:m + 4]))

    # The colour arithmetic is FPlane operator-, operator*(float), operator+.
    imports = {}
    pe2 = pefile.PE(path)
    for e in pe2.DIRECTORY_ENTRY_IMPORT:
        for imp in e.imports:
            if imp.name:
                imports[imp.address] = imp.name.decode()
    need = {"??GFPlane@@QBE?AV0@ABV0@@Z", "??DFPlane@@QBE?AV0@M@Z", "??HFPlane@@QBE?AV0@ABV0@@Z"}
    called = {imports.get(int(t2.split("[")[1].rstrip("]"), 16))
              for t2 in text if t2.startswith("call dword ptr [0x")}
    check("colour lerp uses FPlane -, *(float), +", need <= called,
          f"missing {sorted(need - called)}" if not need <= called else "")

    width = max(len(c[0]) for c in checks)
    ok_all = True
    for label, ok, detail in checks:
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {label:<{width}} {detail}")
    print(f"\nDrawGridSection at RVA {rva:#x} ({len(ins)} instrs disassembled)")
    raise SystemExit(0 if ok_all else 1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Editor.dll")
