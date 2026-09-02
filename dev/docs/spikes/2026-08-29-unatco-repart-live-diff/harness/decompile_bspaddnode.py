"""Decompile the real `bspAddNode` (Editor.dll 0x10034e80) to pseudo-C via angr.

Continuation of the poly-list-order investigation: FilterEdPoly/FilterLeaf (the CSG classify
descent) are now confirmed exact and confirmed blind to the `iPlane` coplanar-chain during
classify (see native-materialize-findings.md, "coplanar `iPlane` node-chain is NEVER read").
The only place either side reads/writes that chain is bspAddNode's own NODE_PLANE insertion
branch. This round reads that whole function (not just the zone/leaf tail block already
disassembly-cited in bspcsg.rs) to check every ordering/placement decision against bspcsg.rs's
own `bsp_add_node` (uedcli-native/src/bspcsg.rs ~285-363).

Same recipe as dev/docs/spikes/2026-09-01-filteredpoly-full-decompile/harness/decompile_fep.py
(CFGFast + normalize() + Decompiler; the normalize() call is REQUIRED before Decompiler or
angr's resilience wrapper silently returns a near-empty stub with no exception).

NEW trap found this round: bspAddNode's codegen hits a SEPARATE silent-failure mode past
normalize() -- a genuine bug in installed `angr` 9.3.3's own `SimStruct.offsets` property
(`sim_type.py:1699-1703`): it computes `align = ty.alignment * self._arch.byte_width` THEN checks
`if align is NotImplemented`, but `SimStruct.alignment`/`SimUnion.alignment` (sim_type.py
~1824-2022) legitimately return the literal `NotImplemented` when every field's own alignment is
unresolved (a struct nested inside a struct angr's type inference gave up on, e.g. some
FArray/TArray-internal field of `UModel`) -- so the multiplication `NotImplemented * int` raises
`TypeError` BEFORE the very guard meant to catch it ever runs. This happens inside the
resilience-wrapped codegen call and angr swallows the exception too, leaving `dec.codegen` as None
outright (worse than the FilterEdPoly round's "near-empty stub" trap -- this one has no text at
all to inspect). Worked around by monkey-patching `SimStruct.offsets` with a corrected version
that checks for `NotImplemented` BEFORE multiplying (i.e. fixing angr's own ordering bug, not
routing around real type info) -- lets codegen finish; a small number of these bottom-typed struct
fields still render as raw-offset/plain-int casts rather than named struct members, so those
specific lines were cross-checked against raw capstone disassembly rather than trusted blind, same
caveat the FilterEdPoly round already flagged for angr decompiles generally.
"""
import angr, logging
from angr import sim_type

logging.getLogger('angr').setLevel(logging.ERROR)


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
            # angr's own bug: multiplies before checking NotImplemented. Guard first.
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

proj = angr.Project('uned/UED22/Editor.dll', auto_load_libs=False)
print("loaded", proj.arch, hex(proj.loader.main_object.min_addr))

cfg = proj.analyses.CFGFast()
print("cfg functions:", len(cfg.functions))

targets = {
    'bspAddNode': 0x10034e80,
}
for name, addr in targets.items():
    fn = cfg.functions.function(addr=addr)
    if fn is None:
        print(name, "NOT FOUND at", hex(addr))
        continue
    print(name, "found:", fn, "size=", fn.size)
    fn.normalize()
    dec = proj.analyses.Decompiler(fn, cfg=cfg.model)
    text = dec.codegen.text if dec.codegen else "<no codegen>"
    print(name, "decompiled length:", len(text))
    outpath = f'dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/{name}.decompiled.c'
    with open(outpath, 'w') as f:
        f.write(text)
    print(f"wrote {outpath} ({len(text)} bytes)")
