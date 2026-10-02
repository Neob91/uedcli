import angr, logging
logging.getLogger('angr').setLevel(logging.ERROR)

proj = angr.Project('uned/UED22/Editor.dll', auto_load_libs=False)
print("loaded", proj.arch, hex(proj.loader.main_object.min_addr))

cfg = proj.analyses.CFGFast()
print("cfg functions:", len(cfg.functions))

targets = {
    'FilterEdPoly': 0x10032bf0,
    'FilterLeaf': 0x10033130,
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
    outpath = f'dev/docs/spikes/2026-09-01-filteredpoly-full-decompile/harness/{name}.decompiled.c'
    with open(outpath, 'w') as f:
        f.write(text)
    print(f"wrote {outpath} ({len(text)} bytes)")
