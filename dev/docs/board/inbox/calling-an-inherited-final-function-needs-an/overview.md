+++
priority = "p3"
kind = "implement"
summary = "calling an inherited final function needs an import too, not just when overriding it"
+++

# calling an inherited final function needs an import too

Found while trying the real UT99 mod `GiveMeItems` (path-to-30-packages corpus candidate) as the
`uscript-texture-import-compiler-integration` item's verification target. NOT a texture-import bug —
`GMIClientWindow.uc`'s `#exec TEXTURE IMPORT` compiles cleanly; this is a separate, pre-existing gap
that blocks the SAME class a few lines later.

`GMIClientWindow.Created()` calls `SetSize(...)`, inherited from `UWindowWindow` (via
`UWindowDialogClientWindow`) with no local override. `lower.py` correctly lowers this as
`EX_FinalFunction` (`SetSize` is declared `final` in `UWindow.u`, confirmed via `ClassGraph`), which
needs an OBJECT ref to the ancestor's `UFunction` export. But `compile.py` only registers that import
in `_super_func_import`, called when THIS class overrides the function — a plain call to an inherited,
un-overridden final function never runs that path, so the resolver (`_build_function_exports`'s
`resolve_inv` / `_multi_function_exports`'s `resolve_inv`) can't find `SetSize` anywhere (not a local
member/func, not already imported) and raises `NotImplementedError: cannot resolve script ref
'SetSize'`.

Likely fix shape: when lowering a call whose target resolves to a `final`, non-local function
(`graph.function(class_name, name)` finds it declared in an ancestor, not this class), register the
same kind of import `_super_func_import` does — either in `lower.py` (mirroring how `extra_deps`
already gets fed back for cross-class `Dependency` entries) or by having the compile.py resolver
consult `graph.function` directly and lazily `_add_import` on a miss (imports must exist before
ordering runs, so this needs to happen during the BUILD pass, not the later resolve pass).

Confirmed by direct testing (not guessed): `graph.function("UWindowDialogClientWindow", "SetSize")`
returns a `FuncBody` with `flags=3` (`FUNC_Final|FUNC_Defined`) once `UWindow.u` is on the search
path — so the resolution mechanism to find it already exists, it's just never invoked for a plain
call.

Not attempted here — out of scope for the texture-import item. `GiveMeItems` still doesn't fully
compile because of this (confirmed on `GMIClientWindow.uc` alone, single-class); the other 6 classes
in the package are untested past this point and may hit further gaps.
