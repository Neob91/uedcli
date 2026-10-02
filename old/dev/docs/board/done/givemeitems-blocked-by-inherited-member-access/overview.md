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

## Fixed (2026-09-13)

Same shape as the final-function fix, mirrored for `EX_InstanceVariable`. `natives.py`'s `ClassSig`
now tracks `member_owner` (casefolded field name -> declaring class's real name) alongside `members`,
inherited down the super chain the same way `members`/`functions` already are; `ClassGraph.member_owner`
exposes it. `lower.py`'s `Symbol` gains an `owner` field (mirrors `CallTarget.owner`), set from
`ClassGraph.member_owner` wherever a member resolves through the graph rather than the class's own
declared members (`Scope.lookup`'s inherited branch, and the new `Scope.member_owner_of` for a
`base.field` access on an object type). `_member_ident(field, owner)` picks the `EX_InstanceVariable`
obj identity: bare for the class's own field, else `mem:<Class>.<Name>` — same shape as
`_final_call_ident`. `compile.py`'s new `_register_member_var_imports` reads that qualifier back off
the lowered tokens and imports the property from its declaring class (Class=its concrete UProperty
subclass via the existing `_SCALAR_KINDS` table, Outer=the declaring class), called from both
`_build_one_function` and `_build_one_state`. `canon()`'s existing `func:` qualifier-strip (added by
the final-function fix, for token-comparison only) is generalized to also strip `mem:` — a decoded
golden token only ever carries the bare field name.

Verified against a live UT99 UCC compile: extended the `UscInheritFinal` fixture itself (rather than
a new one) with `w = WinWidth; h = WinHeight; SetSize(w, h);` in `Created()` — `perm_gate` passes
byte-exact (5 exports, up from 3); the strict gate has the same pre-existing UT99 name-pool diff
already noted for `Fire`, not new. `uedcli/tests/test_uscript_ut99.py`'s `_PACKAGES` entry updated to
`("UscInheritFinal", 5)`.

Retried the real `GiveMeItems` package: the member-variable gap is gone (confirmed on
`GMIClientWindow.uc` alone — it now lowers `Created()`'s `WinWidth`/`WinHeight` reads cleanly and
only fails on an expected same-package cross-class reference, an artifact of compiling one class in
isolation). The full 8-class package still doesn't fully compile — it hits a different, unrelated
blocker: `#exec TEXTURE IMPORT`'s referenced PCX file isn't in the GitHub mirror. Filed separately:
`dev/docs/board/inbox/givemeitems-blocked-by-missing-pcx-texture-asset/`. Full scoped offline suite
green (225 passed), plus the UT99 docker-gated integration tests and
`test_real_stock_functions_breadth` (0 mismatches, no regression).
