# UTServerAdmin: class-reference / meta-class compiler gaps

Found compiling the real UT99 stock package `UTServerAdmin` (4 classes: `UTServerAdmin`,
`UTImageServer`, `UTServerAdminSpectator`, `ListItem`) as a corpus candidate — see
`dev/docs/board/inbox/class-t-typed-variable-s-default-field-needs/` for the starting gap. All
findings below are live-probed against a fresh UED22 or UT99 `UCC.exe` build and pinned by a
committed regression (named per finding). `UTServerAdmin` itself is `perm_gate` byte-exact
(`fixtures/uscript/ut99/UTServerAdmin/`, `test_uscript_ut99.py`).

## 1. `class<T>.default.Field` meta-class tracking

`lower.type_label` collapses every `class<T>` declared type to the bare string `"class"`, losing
`T`. `.default` field access (`class'X'.default.Field`, already implemented) needs the concrete
meta-class to resolve which class's field to read — `class<T>` locals/params/members/metaclass
casts had no way to recover it.

`probe_default_meta_class.py` compiles 4 shapes in one class and decodes their bytecode + the
class's own `Dependencies` array:
- `ViaLocal`: `class<T>` local assigned via a metaclass cast, then `.default` — `ClassContext(0x12)`
  wraps a `LocalVariable` base; Dependencies gets `Class` then the target, same as a literal.
- `ViaInlineCast`: the metaclass cast used INLINE as the `.default` base — same shape.
- `ViaInstance`: an OBJECT-INSTANCE `.default` (`SomeActor.default.Field`) — uses the ORDINARY
  `Context(0x19)`, not `ClassContext`, and records only ONE Dependency entry (no extra `Class`
  one — the base is already a real object reference of that class).
- `ViaNestedField`: a `class<T>`-typed FIELD reached through another `.default` — recurses; each
  level contributes its own `Class`+target pair, inner level first.

Fix: `lower._meta_class_of` (a side-effect-free AST walker: class literal / metaclass cast / bare
`class<T>` symbol via `Symbol.meta` / nested `.default` field via `Scope.member_meta_of`), backed
by a new parallel `member_meta` channel (`natives.ClassSig.member_meta`, `lower.members_meta_of`,
threaded through `Scope`/`build_scope`) alongside the existing type-label one. Every existing
"class"-typed equality check (casts, `_CONV`, value-size) is untouched. `_ex_member`'s `.default`
branch now takes either path (class-typed via `_meta_class_of`, or object-typed via the natural
`self.expr()` type). Regression: `pkg_DefaultMetaClass`
(`test_uscript_package.py::test_class_typed_variable_default_field_access`).

## 2. `ArrayCount(...)` on a `.default` chain

`probe_array_count_default_chain.py`: `ArrayCount(C.Default.Maps)` and
`ArrayCount(S.Default.MapListType.Default.Maps)` both compile to a BARE `IntConstByte`/`IntConst`
— the argument's bytecode is entirely discarded, a pure compile-time substitution of the field's
declared `ArrayDim`. But the class's `Dependencies` array STILL gets every entry evaluating the
argument normally would have produced (verified: `probe_array_count_plain_member.py`'s simpler
`ArrayCount(B.Maps)` records one `Dependency`; the `.default`-chain shapes record the same
`Class`+target pairs `.default` field access does).

Fix: `lower._array_count_dim` (bare name via `Symbol.array_dim`; a `.default` chain via
`_record_default_chain_deps`, which mirrors `_ex_member`'s own recursion but records ONLY the
Dependency side effects, never bytecode) + a new parallel `member_array_dim` channel
(`natives.ClassSig.member_array_dim`, `lower.members_array_dim_of`). A PLAIN (non-`.default`)
member access as the sole argument (`probe_array_count_plain_member.py`'s own shape) is NOT
implemented — not exercised by the real corpus package, raises `NotImplementedError` rather than
guess. Regression: `pkg_ArrayCountDefault`
(`test_uscript_package.py::test_array_count_on_default_chain`).

## 3. `ClassRef.Static.Method(...)`

`probe_class_ref_static_call.py`: calling a function through a `class<T>` reference
(`GameClass.Static.StaticSaveConfig()`) uses the SAME `ClassContext(0x12)` wrapper `.default`
field access uses, here wrapping a `VirtualFunction` call instead of a `DefaultVariable`, and the
same extra `Class` Dependency entry before the target's own. Fix: `lower._call_method` branches on
`base_type == "class"` (resolving the meta via `_meta_class_of`) before its existing object-typed
path. Regression: `pkg_ClassStaticCall` (`test_uscript_package.py::test_class_ref_static_method_call`).

## 4. A class with no exported script body anywhere (`Engine.NetConnection`)

`probe_netconnection_import_only.py`: `NetConnection(x) != None` compiles fine under real UT99 UCC
with ONLY `Core`+`Engine` `EditPackages` loaded, even though NO fetched UT99 `.u` exports a
`NetConnection` class (it's fully native, no `.uc` source ever existed for it) — confirmed by
scanning every stock `.u`'s export table. The golden's own import table names its home package
`Engine`; `Engine.u`'s OWN import table (imports from itself — for some OTHER class's property
type) has an identical `Core.Class`-typed row for `NetConnection` with outer `Engine`.

Fix: `env.class_home_from_imports` scans a package's IMPORT table (not just exports) for a
`Core.Class`-typed row matching the wanted name, resolved to a package name via
`Package.import_package_of`'s existing outer-chain walk — a purely static decode of data already on
disk, no live capture needed. `InstallEnv._import_only_class_to_package`/`import_only_class_package`
(env.py) back `compile._add_import`'s cast-target fallback (previously defaulted to `Core`, wrong);
`natives.ClassGraph._import_only_class_home`/`is_known_class`/`import_only_class_home` back
`Scope.is_class_name`. Regression: `UscNetConnectionProbe`
(`fixtures/uscript/ut99/UscNetConnectionProbe/`, `test_uscript_ut99.py`).

## 5. `"..." $/@ SomeClassRef` (class → string via the concat operators)

`probe_class_to_string_concat.py`: `"prefix=" $ O.Class` (`.Class`, the universal object→class
property) compiles via the ordinary `$` native operator with its class-typed operand wrapped in
`ObjectToString`(0x56) — `_coerce` already handled this (object AND class), but
`natives._match_cost`'s operator-overload SEARCH never allowed a `class` operand to widen into a
`string` parameter, so `binary_operator("$", "string", "class")` found no candidate at all. Fix:
one more `_match_cost` branch, `(is_object(got) or got == "class") and want == "string"`. Regression:
`pkg_ClassToStringConcat` (`test_uscript_package.py::test_class_to_string_concat_operator`).

## 6. `bool(SomeString)`

`probe_string_to_bool.py`: `("string","bool")` = conversion opcode `0x4B` — a free slot between the
already-known `string->int`(`0x4A`)/`string->float`(`0x4C`). Regression: `pkg_StringToBool`
(`test_uscript_package.py::test_string_to_bool_conversion`).

## 7. Case-only field/function-name collisions across import registration sites

Found finishing `UTServerAdmin`: `GameReplicationInfo.MOTDLine1` is READ in one place and
`MOTDline1` WRITTEN in another (same field, `FName` case-insensitive) — `_register_member_var_imports`'s
`ident not in b.imports` check is exact-string, so the two spellings registered as TWO SEPARATE
import rows; downstream ambiguous-name tie-breaks (`_imports_by_display`) and the case-folding
resolver (`_multi_function_exports`'s `import_by_name`) then disagreed on which raw key survived,
a silent `KeyError` at encode time. Fix: `compile._existing_import_key` (case-insensitive lookup),
applied at all three import-registration sites (`_register_member_var_imports`,
`_register_final_call_imports`, `_add_struct_member_import`) — the same rule `_add_import` already
applied to plain class/package names. Pinned by the real `UTServerAdmin` fixture itself (no
isolated controlled repro built — the shape needs two same-package call sites differing only in
field-name case, already exercised end to end by the real package).

## 8. `EX_EatString` for a discarded string-returning call statement

Found finishing `UTServerAdmin`: `Level.ConsoleCommand(...);` used as a bare statement (return
value discarded) wraps in `EatString`(0x0E) — presumably a string needs its refcount released,
unlike a fixed-size scalar. Fix: `lower._st_expr` wraps in `EX_EAT_STRING` when the expression's
type is `"string"`. Only the string case is verified — a discarded struct/array return is
untouched. No isolated controlled fixture (same reasoning as #7 — `UTServerAdmin` exercises it
directly).

## 9. Overriding a `FUNC_Net` function; bare `config;` inheritance

Two smaller gaps, both from `UTServerAdminSpectator extends MessagingSpectator config;`:
- An OVERRIDING function inherits `FUNC_Net`+`FUNC_NetReliable`(`0x40|0x80`) and `RepOffset` from
  the function it overrides — replication is a property of the function itself (its `replication`
  block lives on the DECLARING class), never redeclared per override; `replication` blocks aren't
  implemented in this compiler yet, so this is the only source of `FUNC_Net` for now. Verified on
  `ClientMessage`/`ClientVoiceMessage`/`TeamMessage`/`ReceiveLocalizedMessage`, all overriding
  `PlayerPawn`. Fix: `compile._build_one_function` looks up the overridden `FuncBody` and ORs in its
  `FUNC_Net|FUNC_NetReliable` bits + `RepOffset`; `natives.read_function` now decodes the trailing
  `RepOffset u16` (previously unread).
- A BARE `config;` modifier (no explicit name) INHERITS the super's own `ClassConfigName` rather
  than resetting to `"System"` — `probe_config_name_inheritance.py` confirms
  `Engine.MessagingSpectator`/`Engine.Spectator` are both `'User'` (real UT99 stores
  spectator/messaging prefs in `User.ini`), not the default `'System'`; a class with NO `config`
  keyword at all is left at the old default (unverified for that shape, not touched). Fix:
  `env._config_name`/`ClassInfo.config_name` (env.py) + `compile._class_header`'s new
  `super_config_name` param, threaded from `_ClassUnit.config_name` (same-package super) or
  `env.resolve_class(...).config_name` (cross-package).

Both pinned only by the real `UTServerAdmin` fixture (no isolated controlled repro — small,
mechanical fixes with a single clear real-world shape already exercised end to end).

## 10. `_record_dep` wrongly skipped a self-typed Context

`probe_self_typed_dependency.py`: a controlled self-referencing linked-list class
(`SelfDepNode`, `var SelfDepNode Next;`, a function Contexting through `local SelfDepNode T; ...
T.Next`/`.Tag`) gets 3 deep=0 self-Dependency entries against a fresh UED22 build — found because
the real `ListItem` (UT99, part of `UTServerAdmin`) does this pervasively in its own
`AddElement`/`DeleteElement`/etc. and its class body's `Dependencies` array was missing ~119
entries. An EARLIER version of `lower._record_dep` skipped a Context whose target was the
compiling class itself, on the (unverified) assumption its own deep=1 self-Dependency already
covered it — wrong: real UCC does not dedupe `Dependencies` by class AT ALL (already documented for
cross-class occurrences; this extends it to the self case). The "super" half of the old skip was
dead code — `_call_super` never calls `_record_dep` (it builds `EX_FinalFunction` directly, no
Context). Fix: removed the skip; when the target's `ClassSig` isn't found on disk (a single-class
compile's plain `ClassGraph` never sees the class currently being built), falls back to
`self.scope.class_name` directly. Regression: `pkg_SelfDep`
(`test_uscript_package.py::test_self_typed_context_gets_own_dependency`).
