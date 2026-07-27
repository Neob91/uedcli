+++
priority = "p2"
kind = "docs"
summary = "`deusex-assets-setup.md` \"How it's wired\" cites the RETIRED `packages.substrate_code_dirs` symbol + a stale host-side resolution mechanism"
+++

# `deusex-assets-setup.md` "How it's wired" cites the RETIRED `packages.substrate_code_dirs` symbol + a stale host-side resolution mechanism

Cold review (2026-07-21) found the "Host-side
resolution" bullet asserts `packages.substrate_code_dirs` resolves manifests against
`DeusExAssets/{Textures,Sounds,Music}`; that symbol is retired (`dispatch.py` calls it "the retired
hardcoded `substrate_code_dirs`/`texture_catalog_root`", decisions.md 2026-07-14). Current path is
`packages.editor_search_dirs` + `_remap_to_container` + `ensure_load` over the composed config search
path (architecture.md ~1532). Pre-existing (not introduced by the dev/scripts move); needs the live
symbols verified before rewriting the bullet. Same doc, "How it's wired" section.
