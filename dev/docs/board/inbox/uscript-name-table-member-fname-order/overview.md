+++
priority = "p2"
kind = "finding"
summary = "uscript name-table member FName order interleaves with stock by property type, not a static table"
+++

# uscript name-table member FName order interleaves with stock

Blocks byte-exact NAME table parity for classes with member vars. Import + export tables are byte-exact.

## Evidence (clean UCC compiles, `reference.ucc_compile`)

The name table = `["None"] + msvc_qsort(gather, count-desc)`, gather = global FName registration
order (`ordering.py`). For member-FREE classes a static stock name order reproduces it (UscHello:
name+import+export byte-exact, pinned in `test_uscript_ordering`). For classes with member vars it
does NOT, because member FNames interleave with stock in the pre-sort gather:

- `V1` (`aaa,bbb,ccc` int) name count-1 tier output: `aaa, Core, bbb, System, ccc` — members
  interleave 1:1 with the stock `Core`/`System`, so members are NOT ranked after all stock.
- `V1` (decl `aaa,bbb,ccc`) ≡ `V2` (decl `ccc,bbb,aaa`) byte-identical name tables → member order is
  NOT declaration order.
- `V3` (`mmm`=int,`ddd`=float,`zzz`=string) ≠ `V4` (`zzz`=int,`mmm`=float,`ddd`=string): each orders
  its members int, float, string → order tracks property TYPE, not name.
- `UscVars` (Alpha=int,Beta=float,Gamma=string, Alpha/Beta have defaults) count-1 tier:
  `Gamma, Alpha, Core, System, Beta` — differs from `V3`'s type pattern, so DEFAULTS shift it too.

## Two disproven assumptions

- The original spike premise (invert `msvc_qsort`'s equal-key permutation per count tier, which
  "depends only on tier length") is FALSE: the unstable qsort branches on the whole count vector, so
  a tier's intra-permutation is context-dependent. (Given a fixed count vector it IS a fixed
  position-permutation — labels ride along — which is what makes the reproduction search well-posed.)
- "Own names register last (absent from the global index → sort after all stock)" is FALSE for member
  names, per the interleaving above.

## What this needs

Member-name ordering is a per-package compiler name-encounter artifact (property type + defaults),
not a static table — it belongs in how `compile.py` builds the gather / `ObjInput`s, not in
`global_index.py`. Model it (type-bucket + default handling), then the stock `NAME_ORDER` seed can be
verified/extended against member-bearing goldens.

## Done in the reconstruction pass

`uedcli/uscript/global_index.py`: `OBJECT_ORDER` (reproduces every sampled import table) +
`NAME_ORDER` (member-free seed) + `default_global_index()`. `_gather_names` now gathers import names
too. Pinned in `test_uscript_ordering.py`.
