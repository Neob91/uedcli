+++
priority = "p2"
kind = "debug"
summary = "GiveMeItems blocked by inherited member access (EX_InstanceVariable)"
+++

# GiveMeItems blocked by inherited member access (EX_InstanceVariable)

Fixed the `calling-an-inherited-final-function-needs-an-import` bug (see `USCRIPT-COMPILER.md`'s
package table / `UscInheritFinal` fixture): `lower.py` now tags a final call's `EX_FinalFunction`
obj identity `func:<Class>.<Name>` whenever the target isn't declared/overridden in the class being
compiled (an ordinary call to an inherited function, or any `Super.Foo()` call — which always
targets an ancestor, even when the current class overrides `Foo` under the same name and would
otherwise self-reference); `compile.py`'s `_register_final_call_imports` imports the function object
from its declaring class, deduping onto `_super_func_import`'s existing key format. Verified against
a live UT99 UCC compile (`UscInheritFinal` extends `UWindowDialogClientWindow`, calls `SetSize` and
`Super.Created()`): `perm_gate` passes byte-exact; the strict gate has one pre-existing, unrelated
diff (`UWindow` vs `System` name-table position — the documented UT99 name-pool gap already noted for
`Fire`, not new).

Retried the real `GiveMeItems` package (https://github.com/jpiedra/GiveMeItems) against the UT99
substrate. It does NOT fully compile:

**Inherited member-variable access has the identical gap for `EX_InstanceVariable`.**
`GMIClientWindow.Created()` reads `WinWidth`/`WinHeight` (declared on an ancestor `UWindow` class,
never overridden) and `compile.py`'s `resolve_inv` raises
`NotImplementedError: cannot resolve script ref 'WinWidth' in 'Created'` — same root cause as the
final-function bug (an inherited symbol needs an import compile.py never registers), different
token kind. Confirmed by compiling `GMIClientWindow.uc` alone (with its one `#exec` line stripped)
through `compile_package_dir`.

(A second blocker this item originally listed — `#exec TEXTURE IMPORT` not being wired into
`compile.py` — is now resolved on `master`, landed after this item was written; see
`USCRIPT-COMPILER.md`'s package table and `dev/docs/board/done/uscript-texture-import-compiler-integration/`.
This item now tracks only the inherited-member-variable gap above.)
