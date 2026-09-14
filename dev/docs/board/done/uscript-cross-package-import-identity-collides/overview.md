+++
priority = "p2"
kind = "implement"
summary = "uscript: cross-package import identity collides when two imports share a display name"
+++

# uscript: cross-package import identity collides when two imports share a display name

Found compiling the real UT99 `IpServer` package (`UdpServerQuery.ParseQuery`), after the
cross-package-struct-type fix landed. `Level.Game.GameReplicationInfo.Region` chains three member
accesses; `GameInfo`'s own member `GameReplicationInfo` happens to be named identically to its type,
the class `Engine.GameReplicationInfo`. Compiling raised `KeyError: 'GameReplicationInfo'` in
`compile._import_rec`.

## Root cause (unchanged from the original report)

Two DIFFERENT imports shared the display name `"GameReplicationInfo"`: the class import
(`b.imports["GameReplicationInfo"]`, `class_name="Class"`) and the inherited-member-field import
(`b.imports["mem:GameInfo.GameReplicationInfo"]`, `class_name="ObjectProperty"`). Every step of the
ordering pipeline resolved an import's identity by its bare display name — `compile.
_imports_by_display`'s `by_disp.setdefault(...)` map, and, deeper, `reorder._Decoder.objkey()`/
`objinputs()` (`ObjInput(name=self.idisp(j), ...)`, giving imports NO per-row identity the way an
export gets `ekey`) — so the two rows collided into one `ObjInput`/one `by_disp` entry and one of
them silently dropped out of `imports_order`.

## Fix — FIXED

Gave every import a disambiguated identity end to end, mirroring the export `ekey`/`func:`/`mem:`
pattern already used elsewhere in this compiler:

- `reorder._Decoder` gains `ikey(j) = f"I{j}"` (a per-row import key, parallel to `ekey`). `objkey()`
  resolves a negative ref to `ikey(-ref-1)` instead of the bare display name, so every place that
  decodes a body's `<<UObject` stream (`streams`/`_script_streams`/`_tag_streams`/
  `_class_split_streams`) now carries a precise per-row identity. `objinputs()`'s import loop sets
  `name=ikey(j)`, `display=idisp(j)`, `outer=import_outer_key(j)` (the outer's ikey, not its bare
  spelling).
- `ordering.py`: `by = {o.name: o for o in objs}` (the refcount/gather dict) now never collides for
  two same-named imports. `o.class_name` (always an engine META-TYPE spelling — `IntProperty`,
  `Function`, `Class`, … — never ambiguous) resolves through a separate DISPLAY-keyed map
  (`_reference_counts`'s new `ser_class`, `_gather_names`'s new `by_disp`/`outer_disp`), since it is
  no longer findable via the identity-keyed `by`. The import gather's global-index tie-break
  (`by_obj_index`) now looks up each row's DISPLAY (`o.disp`), not its identity key.
- `reorder.true_order()` returns import rows as `(display, outer display)` pairs — the same
  disambiguation `export_rows` already carried via an outer-chain — instead of bare `list[str]`.
- `compile._imports_by_display` maps a `(display, outer)` pair back to its `b.imports` key: falls
  back to a plain bare-display map when unambiguous (the common case), matches on `(display, outer)`
  when the bare display collides. `compile.py`'s own import `ObjInput` construction (`_general_orders`,
  `_scalar_obj_inputs`) now sets `display=spec.object_name` explicitly too, so the autonomous
  (no-`order_override`) path's import tie-break also resolves against the right global-index entry
  for a `mem:`/`func:`-keyed import, not the mangled internal key.

## Verified

- A new controlled fixture, `UscImportIdentityProbe` (`function int TestFn() { return
  Level.Game.GameReplicationInfo.Region; }`), reproduces the exact collision (both the class import
  AND the field import present, `Region` resolving to the class one) and compiles cleanly. Confirmed
  the OLD code really did crash on this exact shape by monkeypatching the pre-fix
  `_imports_by_display` back in and re-running — reproduces `KeyError: 'GameReplicationInfo'`
  verbatim.
- `perm_gate` (identity/permutation bar) is byte-exact against a fresh UED22 UCC build — both import
  rows land, every reference resolves to the right one.
  `uedcli/tests/test_uscript_import_identity.py` (offline, committed golden + docker-gated fresh
  rebuild). The strict `gate()` does NOT pass — but the one divergence is the import/name table
  ORDER tie-break among count-tied stock objects, the SAME already-tracked, unresolved gap
  `ExtendedBuilders` hits (`extendedbuilders-name-table-qsort-residual/`) — not anything this fix
  touches, and not new: this fixture's import/export/name CONTENT is identical to golden, only the
  table order of some tied entries differs.
- Offline (`test_uscript_*.py`, non-integration) and integration (`-m integration`) suites both
  re-verified green — no regression on any previously byte-exact/perm-exact package.

## IpServer re-attempt

Re-fetched `uned/UT99/`, decompiled `IpServer` fresh (`UdpServerQuery`/`UdpServerUplink`), and
recompiled: `Level.Game.GameReplicationInfo.Region` (`UdpServerQuery.ParseQuery`) no longer raises —
`compile_package_dir` now runs the WHOLE package to completion with no exception (31639 bytes,
golden 31613). It is blocked at `perm_gate` by exactly the SEPARATE, already-tracked gap
(`uscript-struct-member-access-confuses-a-local/`, NOT touched here): `UdpServerUplink.Resolved`'s
`MasterServerIpAddr.Addr = Addr.Addr;` resolves the RHS `Addr.Addr` to the param's own struct instead
of the imported struct field `IpAddr.Addr`. Not a corpus win yet, but the import-identity crash this
item reported is gone and IpServer progresses to the next real gap, as expected.
