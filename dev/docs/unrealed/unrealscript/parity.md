# The `.u` parity gate — exclusion set and pass table

The single statement of what "byte-exact vs UCC" means for the uscript compiler, and which packages
currently meet it. See `uedcli/uscript/gate.py` (`gate` = strict, `perm_gate` = permutation) and
`compile-model.md` for the mechanism.

## Exclusion set

**Only the 16-byte per-build-random package GUID** (header offset 36–51). Two clean UCC compiles of
identical source differ in exactly those 16 bytes and nothing else — confirmed empirically
(`u-format.md`). Table order and FName case are **not** exclusions: they are reproduced from UCC's
real algorithm (the runtime-dumped `GObjNames`/`GObjObjects` order + an instruction-exact CRT `qsort`
port — `compile-model.md`), per the owner's 2026-09-05 ruling to match UCC's algorithm rather than
exclude what we can't yet reproduce.

`perm_gate` (identity/permutation compare, tolerating table order + FName case) exists only as a
**diagnostic stepping-stone**: a package that passes `perm_gate` but not the strict `gate` has real
content parity (bodies, flags, CRCs, bytecode all byte-exact) but an unresolved ordering gap — that
is an OPEN item, not a passing one, and is tracked as such below and in
`dev/docs/board/to-build/uscript-algorithm-fidelity/findings-ordering-re.md`.

## Pass table (2026-09-05)

| Fixture | Strict `gate` | Notes |
|---|---|---|
| UscHello, UscVars, UscBB, UscFn, UscW | ✅ | controlled, single/multi-function classes |
| FrameBuilder | ✅ | real stock DeusEx package |
| RahnemBrushBuilders | ✅ | pins the value-only-name gather-order fix |
| UscSt | perm only | struct-member Next-chain fix landed; ordering not yet re-verified strict |
| DavesBrushBuilders | perm only | name-table order diverges inside one Enum's own value list — same bug class, narrower scope, not yet applied there |
| ExtendedBuilders | perm only | raw byte-count diff (+5 bytes), unrelated to ordering, unexplained |
| Fire (UT99) | not re-verified since the ordering fixes | was perm-only pre-fix |

Any new exclusion beyond the GUID needs the same discipline as `NATIVE-MATERIALIZE.md`'s campaign:
evidence it is functionally inconsequential AND genuinely hard to reproduce, plus the owner's
explicit sign-off — never a silent mask in `gate.py`.
