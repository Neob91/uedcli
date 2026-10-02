#!/usr/bin/env python3
"""Directly EXECUTE the real `FPoly::RemoveColinears` (Engine.dll 0x151090) machine code bytes
against a real captured vertex ring, via `unicorn` x86 emulation of the raw `Engine.dll` image.

WHY. `bspmergecoplanars-8-case-merge-gap-live-traced` follow-up (2026-08-25): a careful hand
disassembly of `RemoveColinears` predicted ACCEPT for a real UNATCO `iLink=1144` merge ring the
live editor demonstrably REJECTS (`TTM AFTERRC rc_eax=0`, `removecolinears_entry_unatco.py`). Rather
than keep re-reading the disassembly by eye (already redone 4+ times, each time missing the same
detail), this runs the ACTUAL bytes and observes what they do — no risk of a misread branch, wrong
stack offset, or wrong calling-convention assumption, because the CPU (emulated) enforces all of
that itself. This is how the real third stage of `RemoveColinears` (a reflex-vertex convexity gate
via `SplitWithPlane`, §4 of `unrealed-geometry-build-map-rebuild-bsp-rebuild/spec.md`) was found:
the emulator's own memory-fault/trace hooks pointed straight at the missed branch.

HOW. Maps `Engine.dll`'s raw PE image at its own declared base (`0x10000000`) — a STATIC mapping,
immune to the runtime `Engine.dll` rebase trap (`re: -0xF00000` at runtime; irrelevant here since we
never touch the live process). Hooks the THREE external (Core.dll) calls `RemoveColinears` actually
makes on the accept path — `FVector::FVector()` (default ctor), `FVector::operator^` (cross
product), `FVector::NormalizeSlow` — with hand-verified calling-convention semantics (thiscall;
`operator^`'s hidden-return-pointer + one explicit arg are BOTH callee-cleaned, `ret 8`, easy to get
off-by-one on since the `call` instruction's own pushed return address sits BELOW them on the
stack). Everything else — `FPoly::DiscardVertexDeltas`, the `VectorsNear`-style helper, and
`FPoly::SplitWithPlane` itself — runs NATIVELY off the mapped image, no reimplementation. The 3
`fs:[0]` SEH-chain instructions in the prologue/epilogue are NOP-patched (irrelevant bookkeeping we
don't want to fake a real segment register for). A dummy zero page at address 0 absorbs writes
through `SplitWithPlane`'s NULL `Front`/`Back` output pointers (this call site is
classification-only; the engine itself never dereferences them beyond that write when no split
fragments are needed by the caller).

Usage:  python3 emulate_removecolinears.py
Requires `pip install unicorn` and this repo's `uned/UED22/Engine.dll` (real UED22 binary, not
committed — see `dev/docs/unrealed/extracting-from-dll.md`).
"""
import struct
import sys
from pathlib import Path

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_32, UcError
from unicorn.x86_const import (
    UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDI, UC_X86_REG_EIP, UC_X86_REG_ESP,
    UC_X86_REG_FS_BASE,
)

ROOT = Path(__file__).resolve().parents[6]
ENGINE_DLL = ROOT / "uned/UED22/Engine.dll"

RC_ENTRY_VA = 0x10151090          # FPoly::RemoveColinears -- confirmed via Engine.dll's own PE
                                   # export table for `?RemoveColinears@FPoly@@QAEHXZ`.
FS_SEH_PATCH_SITES = [(0x1015109a, 6), (0x101510b8, 6), (0x10151225, 7)]  # (VA, byte length)


def f32(x: float) -> float:
    return struct.unpack('<f', struct.pack('<f', x))[0]


def run_remove_colinears(ring: list[tuple[float, float, float]], normal: tuple[float, float, float],
                          *, trace: bool = False) -> tuple[int, list[tuple[float, float, float]]]:
    """Emulate `RemoveColinears` on `ring` (already Normal-relative winding) and return
    `(eax, surviving_verts)` — `eax=0` means the real engine rejects the whole ring."""
    pe = pefile.PE(str(ENGINE_DLL), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    base = pe.OPTIONAL_HEADER.ImageBase
    img = bytearray(pe.get_memory_mapped_image())

    for va, n in FS_SEH_PATCH_SITES:
        off = va - base
        img[off:off + n] = b'\x90' * n

    iat = {}
    for mod in pe.DIRECTORY_ENTRY_IMPORT:
        dll = mod.dll.decode(errors='replace')
        for imp in mod.imports:
            if imp.name:
                iat[imp.address] = f"{dll}!{imp.name.decode(errors='replace')}"
    name_to_slot = {v: k for k, v in iat.items()}

    page = 0x1000
    map_size = ((len(img) + page - 1) // page) * page
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(0x0, page)  # absorbs writes through SplitWithPlane's NULL Front/Back
    mu.mem_map(base, map_size)
    mu.mem_write(base, bytes(img) + b'\x00' * (map_size - len(img)))

    fs_base = 0x00400000
    mu.mem_map(fs_base, page)
    mu.reg_write(UC_X86_REG_FS_BASE, fs_base)

    stack_base, stack_size = 0x00500000, 0x00010000
    mu.mem_map(stack_base, stack_size)

    this_base = 0x00600000
    mu.mem_map(this_base, page)
    mu.mem_write(this_base, b'\x00' * page)

    stub_base = 0x00700000
    mu.mem_map(stub_base, page)
    mu.mem_write(stub_base, b'\xC3' * page)  # safety-net ret trampoline
    func_ctor, func_cross, func_normalize = stub_base + 0x10, stub_base + 0x20, stub_base + 0x30

    def write_iat(slot_va: int, target: int) -> None:
        mu.mem_write(base + (slot_va - base), struct.pack('<I', target))

    write_iat(name_to_slot['Core.dll!??0FVector@@QAE@XZ'], func_ctor)
    write_iat(name_to_slot['Core.dll!??TFVector@@QBE?AV0@ABV0@@Z'], func_cross)
    write_iat(name_to_slot['Core.dll!?NormalizeSlow@FVector@@QAEHXZ'], func_normalize)

    def hook_code(uc, address, size, user_data):
        if address == func_ctor:
            # FVector::FVector(): this=ecx, zero 12 bytes, `ret` (no explicit args to clean).
            ecx = uc.reg_read(UC_X86_REG_ECX)
            uc.mem_write(ecx, b'\x00' * 12)
            esp = uc.reg_read(UC_X86_REG_ESP)
            ret = struct.unpack('<I', uc.mem_read(esp, 4))[0]
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
            uc.reg_write(UC_X86_REG_EIP, ret)
        elif address == func_cross:
            # FVector::operator^(this=ecx='Side' LHS, hidden retbuf ptr, &rhs) -- callee-cleanup:
            # [esp+0]=return addr (pushed by `call` itself, ABOVE the 2 explicit stack args, not
            # below -- the off-by-one that broke this hook on the first attempt), [esp+4]=&retbuf,
            # [esp+8]=&rhs. Confirmed by the call site having no `add esp,N` after the call.
            esp = uc.reg_read(UC_X86_REG_ESP)
            ecx = uc.reg_read(UC_X86_REG_ECX)
            retbuf = struct.unpack('<I', uc.mem_read(esp + 4, 4))[0]
            rhs_ptr = struct.unpack('<I', uc.mem_read(esp + 8, 4))[0]
            ax, ay, az = struct.unpack('<3f', uc.mem_read(ecx, 12))
            bx, by, bz = struct.unpack('<3f', uc.mem_read(rhs_ptr, 12))
            cx = f32(f32(ay * bz) - f32(az * by))
            cy = f32(f32(az * bx) - f32(ax * bz))
            cz = f32(f32(ax * by) - f32(ay * bx))
            uc.mem_write(retbuf, struct.pack('<3f', cx, cy, cz))
            uc.reg_write(UC_X86_REG_EAX, retbuf)
            ret = struct.unpack('<I', uc.mem_read(esp, 4))[0]
            uc.reg_write(UC_X86_REG_ESP, esp + 4 + 8)
            uc.reg_write(UC_X86_REG_EIP, ret)
        elif address == func_normalize:
            ecx = uc.reg_read(UC_X86_REG_ECX)
            x, y, z = struct.unpack('<3f', uc.mem_read(ecx, 12))
            sq = f32(f32(f32(x * x) + f32(y * y)) + f32(z * z))
            if sq < f32(1e-8):
                uc.reg_write(UC_X86_REG_EAX, 0)
            else:
                import math
                inv = f32(1.0 / f32(math.sqrt(float(sq))))
                uc.mem_write(ecx, struct.pack('<3f', f32(x * inv), f32(y * inv), f32(z * inv)))
                uc.reg_write(UC_X86_REG_EAX, 1)
            esp = uc.reg_read(UC_X86_REG_ESP)
            ret = struct.unpack('<I', uc.mem_read(esp, 4))[0]
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
            uc.reg_write(UC_X86_REG_EIP, ret)

    mu.hook_add(UC_HOOK_CODE, hook_code, begin=stub_base, end=stub_base + page)

    if trace:
        def hook_trace(uc, address, size, user_data):
            if address == 0x1015134f:
                print(f"  [convexity-gate check] edi={uc.reg_read(UC_X86_REG_EDI)}")
            if address == 0x10151367:
                eax = uc.reg_read(UC_X86_REG_EAX)
                print(f"  [SplitWithPlane result] eax={eax} (0=Coplanar 1=Front 2=Back 3=Split)")
        mu.hook_add(UC_HOOK_CODE, hook_trace, begin=base + 0x151090, end=base + 0x151400)

    mu.mem_write(this_base + 0xc, struct.pack('<3f', *normal))
    for i, v in enumerate(ring):
        mu.mem_write(this_base + 0x30 + i * 12, struct.pack('<3f', *v))
    mu.mem_write(this_base + 0x1c0, struct.pack('<i', len(ring)))

    ret_addr = stub_base + 0x100
    esp0 = stack_base + stack_size - 0x1000
    mu.mem_write(esp0, struct.pack('<I', ret_addr))
    mu.reg_write(UC_X86_REG_ESP, esp0)
    mu.reg_write(UC_X86_REG_ECX, this_base)

    try:
        mu.emu_start(base + (RC_ENTRY_VA - 0x10000000), ret_addr, timeout=0, count=0)
    except UcError as e:
        print("EMU ERROR:", e, "EIP:", hex(mu.reg_read(UC_X86_REG_EIP)), file=sys.stderr)
        raise

    eax = mu.reg_read(UC_X86_REG_EAX)
    nv_after = struct.unpack('<i', mu.mem_read(this_base + 0x1c0, 4))[0]
    verts = [struct.unpack('<3f', mu.mem_read(this_base + 0x30 + i * 12, 12))
             for i in range(max(nv_after, 0))]
    return eax, verts


if __name__ == "__main__":
    # The real UNATCO iLink=1144 ring, byte-confirmed live against the running editor
    # (`removecolinears_entry_unatco.py`, `RC_ENTRY`/`RC_V0..5`) -- reflex at ring index 0.
    RING = [
        (-2425.910156, 1921.385254, 560.0),
        (-2431.999756, 1952.000000, 560.0),
        (-2591.999756, 1952.000000, 560.0),
        (-2573.731201, 1860.155884, 560.0),
        (-2521.705566, 1782.294312, 560.0),
        (-2408.568604, 1895.431396, 560.0),
    ]
    NORMAL = (-0.0, -0.0, 1.0)
    eax, verts = run_remove_colinears(RING, NORMAL, trace=True)
    print(f"RESULT eax={eax} (0=reject 1=accept) nv_after={len(verts)}")
    for i, v in enumerate(verts):
        print(f"  V{i} = {v}")
