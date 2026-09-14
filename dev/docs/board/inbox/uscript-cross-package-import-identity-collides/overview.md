+++
priority = "p2"
kind = "implement"
summary = "uscript: cross-package import identity collides when two imports share a display name"
+++

# uscript: cross-package import identity collides when two imports share a display name

Found compiling the real UT99 `IpServer` package (`UdpServerQuery.ParseQuery`), after the
cross-package-struct-type fix landed. `Level.Game.GameReplicationInfo.Region` chains three member
accesses; `GameInfo`'s own member `GameReplicationInfo` happens to be named identically to its type,
the class `Engine.GameReplicationInfo`. Compiling raises:

```
KeyError: 'GameReplicationInfo'
```

in `compile._import_rec` (`package_index=0 if spec.outer is None else imp_ref[spec.outer]`) — an
import's `outer` names `"GameReplicationInfo"` but that key never lands in the final `imports_order`.

## Root cause

Two DIFFERENT imports end up with the same **display name** `"GameReplicationInfo"`: the class import
(`b.imports["GameReplicationInfo"]`, `class_name="Class"`) and the inherited-member-field import
(`b.imports["mem:GameInfo.GameReplicationInfo"]`, `class_name="ObjectProperty"`, `object_name=
"GameReplicationInfo"`). `compile._imports_by_display` (used to map `reorder.true_order`'s decoded
import list back onto `b.imports` keys) indexes purely by `spec.object_name.casefold()`:

```python
by_disp: dict[str, str] = {}
for key, spec in b.imports.items():
    by_disp.setdefault(spec.object_name.casefold(), key)
return [by_disp[n.casefold()] for n in display_order]
```

`setdefault` means only the FIRST-inserted of the two collides onto both occurrences in
`display_order`, so one real import key never appears in the rebuilt `imports_order` at all.

The collision goes deeper than this one mapping step: `reorder.py`'s `_Decoder.objinputs()` gives
EVERY import `ObjInput(name=self.idisp(j), ...)` — `idisp(j)` is the bare display name, not a
per-table-index-unique key the way an export gets `ekey(i0) = f"E{i0}"`. `_Decoder.objkey()`
(the general ref-to-identity resolver used walking body streams) resolves an import ref the same way
(`idisp(-ref-1)`). So `order_package`'s own reference-COUNTING (which drives the sort, not just the
final relabeling) already conflates two same-named imports into one `ObjInput` identity upstream of
`_imports_by_display` — a real import gets no distinct identity anywhere in this pipeline once its
display name collides with another import's.

## Why not fixed in the same pass

This is NOT a small, local patch: fixing it properly needs each import to carry a unique internal key
(mirroring `ekey`) threaded through `_Decoder.objkey`/`streams`/`_class_split_streams` (every place
that resolves a raw negative ref into an identity), through `ordering.order_package`'s `ObjInput`
handling (both the gather order and the refcount tally), and through `reorder.true_order`'s `imports`
return shape (today `list[str]`, would need an export-row-like `(display, disambiguator)` shape) before
`compile._imports_by_display` can map back correctly. It may also touch how an import's position in
the dumped `GObjObjects`-style global index is looked up (`compile-model.md`: imports gather in global
`GObjObjects` creation order) if that lookup is *also* currently done by bare name. Scoped out per this
session's instructions (fix at most one small follow-on gap; this one isn't small).

## Repro

Real: `dev/docs/spikes/.../IpServer/` decompiled sources (not committed, regenerate with
`ucc_decompile_ut99(container, "IpServer")` per `test_ipserver_roundtrips`) — `UdpServerQuery.uc`'s
`ParseQuery` hits it via `Level.Game.GameReplicationInfo.Region`/`.ServerName`/etc. Not yet reduced to
a minimal controlled fixture.

Blocks `IpServer` from a corpus win (on top of the struct-member/local-name-collision gap logged
separately, `uscript-struct-member-access-confuses-a-local/`).
