"""Decompile `FPoly::Transform` (Engine.dll) to check its vertex-transform arithmetic order
against `uedcli-native/src/fpoly.rs::FPoly::transform`.

Address: `Engine.dll` RVA `0x152360` (cited in `dev/docs/native-materialize-findings.md` and
`bspbrushcsg-filter-decode.md`'s IAT table, slot `0x100cee3c`), i.e. VA `0x10152360` at the
project's standard load base `0x10000000` (Editor.dll and Engine.dll both load there per
`angr.Project(..., auto_load_libs=False)`).  `FPoly::CalcNormal` (Engine.dll RVA `0x150510`,
VA `0x10150510`) decompiled alongside it for context (already ported in `fpoly.rs::calc_normal`
with a pinned doc comment/tests -- decompiled here only to sanity-check the harness against a
known-correct function).

Same recipe + `SimStruct.offsets` monkeypatch as
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/decompile_bspaddnode.py` (angr 9.3.3's
own bug: `sim_type.py`'s `SimStruct.offsets` multiplies `ty.alignment * byte_width` BEFORE
checking whether `alignment` came back the literal `NotImplemented`, raising `TypeError` and
silently killing codegen for any function touching a bottom-typed nested struct field).
"""
import angr
import logging
from angr import sim_type

logging.getLogger("angr").setLevel(logging.ERROR)

DLL = "uned/UED22/Engine.dll"
BASE = 0x10000000

TARGETS = {
    "FPoly__Transform": BASE + 0x152360,
    "FPoly__CalcNormal": BASE + 0x150510,
}


def _patched_offsets(self):
    if self._arch is None:
        raise ValueError("Need an arch to calculate offsets")
    offsets = {}
    bitoffset_so_far = 0
    for name, ty in self.fields.items():
        ty_size = ty.size
        if ty_size is None:
            continue
        if not self._pack and ty_size > 0:
            align = ty.alignment
            align = 1 if align is NotImplemented else align * self._arch.byte_width
            if bitoffset_so_far % align != 0:
                bitoffset_so_far += align - bitoffset_so_far % align
            offsets[name] = bitoffset_so_far // self._arch.byte_width
            bitoffset_so_far += ty_size
        else:
            offsets[name] = bitoffset_so_far // self._arch.byte_width
            bitoffset_so_far += ty_size
    return offsets


sim_type.SimStruct.offsets = property(_patched_offsets)


def main():
    proj = angr.Project(DLL, auto_load_libs=False)
    print("loaded", proj.arch, hex(proj.loader.main_object.min_addr), flush=True)
    cfg = proj.analyses.CFGFast()
    print("cfg functions:", len(cfg.functions), flush=True)

    for name, addr in TARGETS.items():
        fn = cfg.functions.function(addr=addr)
        if fn is None:
            print(f"{name}: NOT FOUND at {hex(addr)}")
            continue
        print(f"{name}: found at {hex(fn.addr)}, size~{fn.size}")
        fn.normalize()
        dec = proj.analyses.Decompiler(fn, cfg=cfg.model)
        text = dec.codegen.text if dec.codegen else None
        if not text:
            print(f"  codegen EMPTY/None for {name}")
            continue
        out = f"{name}.decompiled.c"
        with open(out, "w") as f:
            f.write(text)
        print(f"  wrote {out} ({len(text)} bytes)")


if __name__ == "__main__":
    main()
