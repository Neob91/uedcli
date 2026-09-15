"""UT99 corpus: uedcli's compiler is byte-exact vs UT99's own UCC, via `gate.perm_gate`.

Two layers:
  1. The UT99 reference toolchain (`reference_ut99`): UT99's own `UCC.exe`+DLLs+`.u` (fetched by
     `uedcli/uscript/fetch_ut99.sh` into `uned/UT99/System/`, gitignored) compile/decompile UT99
     packages. Needs docker + the substrate.
  2. uedcli's `compile_package_dir` vs a committed UCC golden. Each fixture is
     `fixtures/uscript/ut99/<Pkg>/`: the `.uc` sources plus `<Pkg>.u`, a fresh `ucc_compile_ut99` of
     exactly those sources. The OFFLINE check needs no docker but does need the substrate `.u` on the
     search path (to resolve supers); a DOCKER-gated check rebuilds the golden and re-gates.

Fixtures (each isolates a compiler gap fixed for the first UT99 packages):
  - `Fire`         - 6 native texture classes: a non-scalar struct member (ESpark in `Spark`),
                     `array<Spark>`, native-class ObjectFlags/ClassFlags/PackageImports, explicit-only
                     defaults.
  - `UscEnumDef`   - an inherited enum-name default (`RemoteRole=ROLE_SimulatedProxy`) resolved to its
                     byte ordinal against the inherited `ENetRole`.
  - `UscTextPos`   - function Line/TextPos located by the actual declaration, not a bare name-`(`
                     substring (here `Beta` is called before it is declared).
  - `UscInheritFinal` - calling an inherited `final` function never overridden locally (an ordinary
                     call and a `Super.` call to the SAME name as a local override), and reading an
                     inherited member variable (`WinWidth`/`WinHeight`) never declared locally — both
                     need an import of the object from its declaring class (`UWindowDialogClientWindow`
                     / `UWindowWindow`) — the real-world case is `GiveMeItems`' `GMIClientWindow.uc`.
  - `UscAutoEmitDefaultsUT99` - UT99's `UCC.exe` never auto-emits a type-zero `defaultproperties` tag
                     for a plain class's unset own property (UED22's own `UCC.exe` does) — one class,
                     an object + every scalar type, an explicit empty `defaultproperties{}` block, no
                     tag for any of them (`compile._auto_emit_defaults`, `substrate="ut99"`).
  - `UWeb`         - the real stock UT99 package (7 classes): the corpus win this fixture set was
                     building toward. `perm_gate` byte-exact; the strict gate's only residual is the
                     pre-existing UT99 own-name-pool gap already noted for `Fire` (`USCRIPT-COMPILER.md`).
  - `UscIpAddrProbe` - a member var AND a function param typed to a struct declared in a DIFFERENT
                     package (`IpDrv`'s `IpAddr`, on `InternetLink`), plus struct-member access on
                     both (`.Addr`/`.Port`) - the gap real UT99 `IpServer.UdpServerUplink.
                     MasterServerIpAddr` hit (`_resolve_var_type` only resolved a struct type declared
                     in the CURRENTLY-COMPILING package). The param is named `Addr`, same as `IpAddr`'s
                     own field `Addr` (real `IpServer.UdpServerUplink.Resolved`'s exact shape) - a bare
                     `StructMember` field identity used to resolve to the PARAM's own export instead of
                     the struct field's import (`uscript-struct-member-access-confuses-a-local`, now
                     fixed: the identity is always qualified `smem:<Struct>.<Field>`). `perm_gate`
                     byte-exact; the strict gate's only residual is the same pre-existing UT99
                     own-name-pool gap as `Fire`/`UWeb`.
  - `IpServer`     - the real stock UT99 package (2 classes, `UdpServerQuery`/`UdpServerUplink`) the
                     `UscIpAddrProbe`/assert/byte-to-string/static-call/import-identity gaps above were
                     all found chasing. With the struct-member fix it compiles end to end and reaches
                     `perm_gate` byte-exact; the strict gate's only residual is the same pre-existing
                     UT99 own-name-pool gap as `Fire`/`UWeb`.
  - `NoGunsMutator` - a real community mutator (github.com/vumaq/ut99-mutators), hand-authored with NO
                     `defaultproperties` block and a trailing blank line in the source file — a shape
                     no prior fixture exercised (every earlier source always had a `defaultproperties`
                     tag, even an empty one). `compile._script_text`'s no-`defaultproperties` branch
                     returned the raw source verbatim, so the stored `ScriptText` (and its
                     `appStrCrc`-derived self-dependency CRC) carried an extra trailing blank line real
                     UCC's own capture drops. Fixed: that branch now strips trailing wholly-blank
                     line(s), keeping exactly the newline terminating the last real line. `perm_gate`
                     byte-exact; the strict gate's only residual is the same pre-existing UT99
                     own-name-pool gap as `Fire`/`UWeb`/`IpServer` (a `Name` literal, `'Enforcer'`,
                     naming a real `BotPack` class the UT99 name-pool dump doesn't cover).
  - `ASPMutator`   - a real community mutator (github.com/rxut/AdvancedSpawnPoints), a `Botpack`-
                     dependent mutator (`TournamentPlayer`/`UTTeleportEffect`/`TeamGamePlus`) that
                     needed the Botpack-load fix (`fetch_ut99.sh`'s `Sounds/` fetch, below) plus five
                     further real gaps: `class<T>`/cross-package type discovery only walked a class's
                     own super, not member/param/local var TYPES (`compile._extra_super_packages`,
                     now transitive via a resolved class's own `package_imports`); `Vect(x,y,z)`/
                     `Rot(p,y,r)` literals were entirely unimplemented (`EX_VectorConst`/
                     `EX_RotationConst`, `lower._vec_or_rot_literal`); a Vector/Rotator operand of the
                     string-concat operators (`@`/`$`) needs `EX_VectorToString`(0x58)/
                     `EX_RotatorToString`(0x59), not in the flat scalar `_CONV` table; a compound-
                     assignment operator (`-=`/`*=`/…) must match its `out` LHS param EXACTLY, never
                     widen it the way an ordinary binary operator's overload search does
                     (`Catalog.compound_assign_operator`); a `for` loop's UPDATE clause's own Context
                     dependency is recorded TWICE by real UCC — once in source-textual header order
                     (right after the init clause's) and again at its natural bytecode-emission
                     position after the body (`lower._st_for`); and an EXPLICIT default assignment
                     equal to its own type's zero value gets no defaultproperties tag under UT99
                     (`bDebugMode=False` alongside `bEnabled=True` — same sibling `var` line, only the
                     zero one is dropped), extending the existing "UT99 never auto-emits a zero
                     default" rule from unset properties to explicitly-assigned-zero ones too
                     (`compile._emit_default`). `perm_gate` byte-exact; the strict gate's only residual
                     is the same pre-existing UT99 own-name-pool gap as the other UT99 packages.
  - `UTServerAdmin` - a real stock UT99 package (4 classes: `UTServerAdmin`/`UTImageServer`/
                     `UTServerAdminSpectator`/`ListItem`), needed eight further real gaps, all now
                     fixed: (1) `class<T>`-typed local/param/member/metacast `.default` field access
                     (`TempClass.Default.GameName`) — `type_label` collapses every `class<T>` to the
                     bare string "class", losing `T`; `lower._meta_class_of` recovers it via a
                     side-effect-free AST walk (a class literal, a metaclass cast, a declared
                     `class<T>` symbol, or, recursing, a nested `class<T>`-typed FIELD read through
                     another `.default`), backed by a NEW parallel `member_meta`/`member_array_dim`
                     channel (`natives.ClassSig`) alongside the existing type-label one — every
                     existing "class"-typed check (casts, `_CONV`, value-size) stays untouched. An
                     OBJECT-INSTANCE `.default` (`SomeActor.default.Field`) uses the ORDINARY
                     Context(0x19) instead of ClassContext(0x12) and records only ONE Dependency
                     entry (no extra "Class" one) — live-probed, both shapes. (2) `ArrayCount(...)` — a
                     pure COMPILE-TIME constant substitution (the field's declared ArrayDim, via the
                     same `member_array_dim` channel), yet still records every Dependency entry
                     evaluating its argument normally would have (`lower._array_count_dim`/
                     `_record_default_chain_deps`) — live-probed. (3) `ClassRef.Static.Method(...)` (a
                     function called dynamically through a `class<T>` reference) uses the SAME
                     ClassContext(0x12) wrapper `.default` uses, wrapping a VirtualFunction call
                     instead of a DefaultVariable (`lower._call_method`) — live-probed. (4) a class
                     with NO exported script body ANYWHERE on the search path but reachable as an
                     IMPORT elsewhere (`Engine.NetConnection`, fully native, no `.uc` source at all) is
                     still a valid cast target — `env.class_home_from_imports` scans every package's
                     own IMPORT table (not just exports) for a `Core.Class`-typed row, a purely static
                     decode of data already on disk, no live capture needed. (5) `"..." $/@
                     SomeClassRef` (a `class`-typed operand of the string-concat operators) — the
                     `_match_cost` overload search never allowed `class` to widen into `string`, even
                     though `_coerce`'s `ObjectToString` codegen already handled it — live-probed. (6)
                     `bool(SomeString)` — `("string","bool")` = `0x4B`, a free slot between the
                     already-known `string->int`(`0x4A`)/`string->float`(`0x4C`) — live-probed. (7) two
                     SOURCE occurrences of the SAME inherited field/function/struct member differing
                     only in CASE (`GameReplicationInfo.MOTDLine1` read, `.MOTDline1` written) used to
                     register as TWO SEPARATE (ambiguous) import rows — `compile._existing_import_key`
                     dedupes case-insensitively (`FName` identity) at all three registration sites
                     (member/final-call/struct-member imports), the same rule `_add_import` already
                     applied to plain class/package names. (8) a bare expression-statement whose call
                     RETURNS A STRING (`Level.ConsoleCommand(...);`, result discarded) wraps in
                     `EatString`(0x0E) — live-probed; only the string case is verified, any other
                     discarded non-trivial type is untouched. Two further, smaller gaps: an
                     OVERRIDING function inherits `FUNC_Net`(+`FUNC_NetReliable`) and `RepOffset` from
                     the function it overrides (replication is a property of the function itself, not
                     redeclared per override — `replication` blocks aren't implemented yet, so this is
                     the only source for now) — live-probed against real `UTServerAdminSpectator`
                     overriding `PlayerPawn`'s messaging functions; a bare `config;` modifier (no
                     explicit name) INHERITS the super's `ClassConfigName` (`Engine.MessagingSpectator`
                     is `config(User)`, not the default `System`) rather than resetting to `System` —
                     live-probed. A NINTH, unrelated bug found along the way: `_record_dep` used to
                     SKIP a Context whose target was the COMPILING CLASS ITSELF (assumed redundant with
                     its own deep=1 self-Dependency entry) — real UCC does NOT dedupe by class at all,
                     confirmed on `ListItem` (a self-referencing linked-list class whose own methods
                     Context through `local ListItem T; ... T.Next`/`.Tag` throughout) and a controlled
                     probe (`SelfDepNode`); the "super" half of the old skip was dead code (`Super.Foo()`
                     never goes through `_record_dep` at all). `perm_gate` byte-exact against a fresh
                     UT99 UCC build; the strict gate's only residual is the same pre-existing UT99
                     own-name-pool gap as the other UT99 packages.
  - `UscNetConnectionProbe` - controlled: pins gap (4) from `UTServerAdmin` above in isolation --
                     `NetConnection(O) != None` (a cast to a class with NO exported script body
                     ANYWHERE on the search path, fully native, no `.uc` source at all) resolves via
                     `env.class_home_from_imports` scanning another package's own IMPORT table.
  - `SeanMutator`, `ProtectSeanMutator`, `VampireSeanMutator` - three real community mutators
                     (github.com/smcl/ut99-dev, single-class each). `ProtectSeanMutator`/
                     `VampireSeanMutator` already passed `perm_gate` with no compiler change.
                     `SeanMutator`'s `HelloMut.uc` has NO `defaultproperties` block and NO trailing
                     newline at all (ends `}` with nothing after) -- a source shape narrower than
                     `NoGunsMutator`'s (a trailing BLANK LINE, at least one newline present). Real
                     UCC's own `ScriptText` capture still ends with exactly one line terminator: it
                     ADDS one where the source has none, the same rule (not a special case) that
                     already collapsed `NoGunsMutator`'s multiple trailing newlines to one --
                     `compile._script_text`'s no-newline branch now appends one instead of returning
                     the source unchanged.
  - `CrouchBlocksDamage` - a real community mutator (github.com/joeytwiddle/code,
                     code/unrealscript/CrouchBlocksDamage) with its `defaultproperties` block placed
                     BEFORE its functions in source order (every prior fixture had it last, the
                     conventional position) -- a shape `_script_text` mishandled: it treated
                     `defaultproperties` as a TRUNCATION point (drop everything from there on), so
                     the functions declared after it vanished from `ScriptText` and `_function_positions`
                     couldn't locate them. Real UCC instead EXCISES just the block itself (the
                     `defaultproperties` keyword through its matching `}`, plus exactly one immediate
                     trailing line terminator) and keeps whatever comes after, renumbering it as if the
                     block had never been there -- confirmed byte-exact (`ScriptText` content AND every
                     later function's `Line`/`TextPos`) against a live UT99 UCC build. Fixed:
                     `compile._skip_defaultproperties_block` finds the block's true end (skipping `//`/
                     nesting `/* */` comments and `"..."` strings the way the real lexer does, so a
                     brace inside one doesn't perturb the depth count), and `_script_text` splices the
                     block out instead of truncating there. `perm_gate` byte-exact; the strict gate's
                     only residual is the same pre-existing UT99 own-name-pool gap as the other UT99
                     packages.
  - `IdcKicker`    - a real community mutator (github.com/joeytwiddle/code,
                     code/unrealscript/IdcKicker): static-array `config` vars (`String[256]`), `~=`,
                     `Super.PostBeginPlay()`/`Super.Mutate()`, `FRand()`. Already `perm_gate`
                     byte-exact with no compiler change; residual is the same pre-existing UT99
                     own-name-pool gap as the other UT99 packages.
  - `NerfSniper`   - a real community mutator (github.com/joeytwiddle/code,
                     code/unrealscript/NerfAmmo), `Botpack`-dependent: a WRITE through a
                     `class'X'.default.Field` chain (`class'BulletBox'.default.MaxAmmo = MaxAmmo;`,
                     the lvalue counterpart of the `.default` READ chains `UTServerAdmin` exercised).
                     Already `perm_gate` byte-exact with no compiler change; residual is the same
                     pre-existing UT99 own-name-pool gap as the other UT99 packages.
  - `UscFoldProbe` - controlled: pins the fix for a numeric-literal-operand CONSTANT-FOLD bug found
                     compiling `MessageAdmin` (below). `lower._binary` used to fold a constant operand
                     into an operator's param type (e.g. the `44` in `44 + w`, an `int` literal against
                     a `float` var) UNCONDITIONALLY. Live-probed (six functions, `x`/`i` targets
                     crossed with a var and a native-call right operand): UCC folds the literal into a
                     bare `FloatConst` ONLY when the operator's own result needs no FURTHER outer
                     conversion (assigned straight to a `float`); when the assignment target is `int`
                     (needing an outer `float->int` conversion on the whole expression), the literal
                     instead compiles at its OWN natural type (`IntConst`) with an explicit INNER
                     `int->float` conversion, exactly like the non-literal right operand always gets.
                     Fixed: `expr()` grew an optional `expected` type (threaded from `_st_assign`/
                     `_st_return`/`_value` -- the `for`-loop init/update clause's own assignment
                     lowering, a sibling `_st_assign` originally missed -- the three contexts that
                     already know a target type up front), read only by `binary`/`paren` nodes
                     (`lower._should_fold`); `unary`'s preoperator fold stays UNCONDITIONAL (accepts
                     `expected` for dispatch-signature uniformity but ignores it) -- the live probes
                     only exercised binary operators, so extending the same gate to unary was an
                     unverified generalisation, caught in review and reverted. Two more functions
                     (`TestForInit{Float,Int}Target`, a `for (x = 44 + w; ...)` init clause) pin the
                     `_value` fix specifically. Function-call-argument position isn't threaded yet (no
                     call site currently passes `expected` into `_coerce_args`'s callers) -- same
                     open gap as before this fix for that one context, not chased here. `perm_gate`
                     byte-exact; the strict gate's only residual is the same pre-existing UT99
                     own-name-pool gap as the other UT99 packages.
  - `MessageAdmin` - a real community mutator (github.com/joeytwiddle/code,
                     code/unrealscript/MessageAdmin) -- the real package that surfaced the
                     `UscFoldProbe` bug above (`i = 256*FRand();`, where the previous unconditional
                     fold shifted every later jump target in the function by 1 byte). `perm_gate`
                     byte-exact; residual is the same pre-existing UT99 own-name-pool gap as the
                     other UT99 packages.
  - `NoPistonCamping`, `ForceBehindView` (github.com/joeytwiddle/code, code/unrealscript/
                     NoPistonCamping and WeirdMuts/ForceBehindView.uc), `TeamSwitcher`,
                     `RedirectPlayers` -- real community mutators, all already `perm_gate` byte-exact
                     with no compiler change (the same residual UT99 own-name-pool gap only).
                     `ForceBehindView`'s package name differs from its containing repo directory
                     (`WeirdMuts`) -- the compiled package name is always the CLASS name, not the
                     directory.
  - `UscRandomMutatorsGaps` - controlled: pins three further gaps found compiling `RandomMutators`
                     (below). (1) An explicit empty scalar default (`Field=`, nothing after the `=`
                     before the closing `}`/next line -- `parser.py` already parsed this as
                     `Expr(op="empty")` for a DECOMPILED native/pointer field's default; real UCC
                     also accepts it HAND-AUTHORED for `String`/`Name` fields, compiling to the type's
                     zero value -- `compile._scalar_default` now returns `_SCALAR_ZERO[ptype]` for
                     `op == "empty"` on those two types (no legal empty literal exists for the
                     others, left raising). (2) `Obj.Class.Name` -- `.Class` reads as an ordinary
                     object member (type `"class"`, `ClassProperty`); a further `.Field` off it used
                     to raise (`lower._ex_member` only handled struct/object bases). `Class` itself
                     (`UState`/`UStruct`/`UField`/`UObject`) isn't indexed (noexport, no visible
                     script) so the MEMBER LOOKUP resolves against `Object` (everything reachable
                     this way, e.g. `Name`, is inherited from it); the two extra Dependency entries
                     a `.Class`-chained access adds (live-probed in three isolated steps --
                     `UscCastDepProbe`, `UscClassOnlyDepProbe`, `UscClassNameDepProbe2`/
                     `UscClassNameDepProbe`, all under `dev/docs/spikes/2026-09-14-randommutators-
                     class-name-dep/`) are `Core.Class` then the chain's REAL underlying class
                     (`Mutator`, not `Object`, `Name`'s declaring class) -- only resolvable when the
                     base is textually `X.Class`, so any OTHER source of a `"class"`-typed base falls
                     back to `Object`, unverified. A plain cast (`Mutator(x)`/`class<Mutator>(x)`)
                     was FIRST measured (wrongly) as adding two Dependency entries of its own --
                     confounded by a combined probe that also exercised `.Class.Name` in the same
                     function; an isolated probe (`UscCastDepProbe`) showed a cast adds NONE, and
                     that guess was reverted before landing. (3) `class:<Name>` cast/metaclass-cast
                     import resolution (`compile._resolve_class_ident`, the multi-class build path
                     `compile_package_dir` always uses) looked an import up by EXACT ident text,
                     unlike its own same-package-sibling check one line above (already casefold) and
                     unlike the single-class path's equivalent resolvers (`_build_function_exports`/
                     `_build_state_exports`, already casefold) -- a source spelling that differs in
                     case from the class's canonical import spelling (`mutator(o)` for `Engine.
                     Mutator`) raised `KeyError`. Fixed: `_resolve_class_ident` takes the same
                     `import_by_name` casefold map its siblings already build. `perm_gate` byte-exact;
                     residual is the same pre-existing UT99 own-name-pool gap as the other UT99
                     packages.
  - `RandomMutators` (github.com/joeytwiddle/code, code/unrealscript/RandomMutators) -- the real
                     package `UscRandomMutatorsGaps` was built to isolate, plus a FOURTH gap of its
                     own: a duplicate, commented-out declaration of `SplitString` sits textually
                     BEFORE the real one (`/* function int SplitString(...) {...} */` immediately
                     followed by the real `function int SplitString(...) {...}`) -- `compile.
                     _function_positions`'s declaration search was a plain regex over raw source text,
                     blind to comments, so it matched the FAKE declaration first and computed the
                     real function's Line/TextPos wrong. Fixed: `compile._mask_lexical_noise` builds a
                     same-length, comment/string-blanked view of the source (mirroring the real
                     lexer's own rules -- `lexer.py`'s `_skip_block_comment` NESTS `/* */`, unlike the
                     narrower single-`find("*/")` scan this replaces), and `_function_positions`
                     searches/scans that instead of the raw text throughout (including the
                     first-executable-statement skip loop, simplified to a plain whitespace skip now
                     that comments are already blanked). `perm_gate` byte-exact; residual is the same
                     pre-existing UT99 own-name-pool gap as the other UT99 packages.
  - `ArenaFallback` (github.com/joeytwiddle/code, code/unrealscript/ArenaFallback), `Botpack`-
                     dependent: a bare `return;` as the LAST statement inside a `foreach` block. Real
                     UCC releases the iterator first (`IteratorPop`) before the `Return` token --
                     `break` already did this (jumping to a target placed right before the loop's own
                     trailing `Pop`), but a `return` exits directly, bypassing that flow-through.
                     Fixed: `lower._Lowerer.foreach_depth` counts active `foreach` nesting;
                     `_st_return` emits one `IteratorPop` per enclosing level (innermost first)
                     before the `Return` token. `perm_gate` byte-exact; residual is the same
                     pre-existing UT99 own-name-pool gap as the other UT99 packages.
  - `UscBareDefaultProbe` - controlled: pins a bare `default.Field` access (implicit `Self`, no
                     explicit class/object base -- `return default.Count;`), found compiling `Resize`
                     (github.com/joeytwiddle/code). A DIFFERENT shape than `X.default.Field`
                     (`lower._ex_member`'s existing two-level check, keyed on `inner.op == "member"`):
                     here `inner.op == "default"` directly (the parser's own leaf node for the bare
                     `default` keyword). Live-probed: a bare `DefaultVariable`(0x02) token, no Context
                     wrapping at all -- the same shape as any other own-member read
                     (`lower._ex_name`'s `EX_INSTANCE_VARIABLE` case), just the Default op instead.
                     `perm_gate` byte-exact; residual is the same pre-existing UT99 own-name-pool gap.
  - `UscFloatByteProbe` - controlled: pins the `float -> byte` conversion opcode, `0x43` (live-probed:
                     `b = f;`, a free slot right before the already-known `float -> int` at `0x44`),
                     found compiling `Resize` (`Other.SoundVolume = Other.SoundVolume / Scale;`, a
                     `byte` Actor property assigned a float division result). `perm_gate` byte-exact;
                     residual is the same pre-existing UT99 own-name-pool gap.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import perm_gate
from uedcli.uscript.reference_ut99 import (UccError, ucc_compile_ut99, ucc_decompile_ut99,
                                           ut99_container, ut99_sounds_dir, ut99_substrate_dir)
from uedcli.uscript.serialize import serialize

_PKG_MAGIC = 0x9E2A83C1
_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript" / "ut99"

# (package, export count) - the byte-parity corpus; count pins export-identity coverage.
_PACKAGES = [("Fire", 108), ("UscEnumDef", 2), ("UscTextPos", 12), ("UscInheritFinal", 5),
            ("UscAutoEmitDefaultsUT99", 7), ("UWeb", 154), ("UscIpAddrProbe", 5), ("IpServer", 154),
            ("NoGunsMutator", 9), ("ASPMutator", 61), ("UTServerAdmin", 353),
            ("UscNetConnectionProbe", 5), ("SeanMutator", 4), ("ProtectSeanMutator", 13),
            ("VampireSeanMutator", 13), ("CrouchBlocksDamage", 16), ("IdcKicker", 22),
            ("NerfSniper", 10), ("UscFoldProbe", 19), ("MessageAdmin", 41),
            ("NoPistonCamping", 24), ("ForceBehindView", 16), ("TeamSwitcher", 24),
            ("RedirectPlayers", 14), ("UscRandomMutatorsGaps", 14), ("RandomMutators", 38),
            ("ArenaFallback", 42), ("UscBareDefaultProbe", 5), ("UscFloatByteProbe", 5)]

# Extra stock EditPackages a fixture's super chain needs loaded (`_edit_packages_upto`'s
# content-safe base only covers Core/Engine/Editor) — only needed for the DOCKER-gated rebuild.
_DEPS: dict[str, tuple[str, ...]] = {"UscInheritFinal": ("UWindow",), "UWeb": ("IpDrv",),
                                     "UscIpAddrProbe": ("IpDrv",), "ASPMutator": ("Botpack",),
                                     "UTServerAdmin": ("UWindow", "IpDrv", "Botpack"),
                                     "NerfSniper": ("Botpack",), "NoPistonCamping": ("Botpack",),
                                     "ArenaFallback": ("Botpack",)}


def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _substrate_present() -> bool:
    try:
        ut99_substrate_dir()
        ut99_sounds_dir()
        return True
    except UccError:
        return False


def _sources(pkg: str) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted((_FIX / pkg).glob("*.uc"))}


def _compile(pkg: str) -> bytes:
    env = InstallEnv([str(ut99_substrate_dir())], substrate="ut99")
    return serialize(compile_package_dir(_sources(pkg), env, package_name=pkg))


# ── offline: compiler vs committed golden (needs the substrate .u, not docker) ────────────────────
@pytest.mark.skipif(not _substrate_present(),
                    reason="needs the fetched UT99 substrate (uedcli/uscript/fetch_ut99.sh)")
@pytest.mark.parametrize("pkg,exports", _PACKAGES)
def test_ut99_offline_byte_exact(pkg: str, exports: int):
    golden = (_FIX / pkg / f"{pkg}.u").read_bytes()
    mine = _compile(pkg)
    assert struct.unpack_from("<I", mine, 0)[0] == _PKG_MAGIC
    assert struct.unpack_from("<I", golden, 20)[0] == exports, f"{pkg}: golden export count"
    r = perm_gate(mine, golden)
    assert r.passed, f"{pkg}: " + " | ".join(r.messages)


# ── docker-gated: rebuild the golden with UT99's UCC and re-gate (guards golden drift) ─────────────
@pytest.mark.integration
@pytest.mark.skipif(not (_docker_up() and _substrate_present()),
                    reason="needs a live docker daemon and the fetched UT99 substrate")
@pytest.mark.parametrize("pkg,exports", _PACKAGES)
def test_ut99_matches_fresh_ucc(pkg: str, exports: int, tmp_path):
    with ut99_container(state_dir=tmp_path) as c:
        fresh = ucc_compile_ut99(c, pkg, _sources(pkg), deps=_DEPS.get(pkg, ()))
    r = perm_gate(_compile(pkg), fresh)
    assert r.passed, f"{pkg} vs fresh UCC: " + " | ".join(r.messages)


# ── the UT99 reference toolchain is self-consistent (compile/decompile round-trip) ────────────────
@pytest.mark.integration
@pytest.mark.skipif(not (_docker_up() and _substrate_present()),
                    reason="needs a live docker daemon and the fetched UT99 substrate")
def test_trivial_compile(tmp_path):
    with ut99_container(state_dir=tmp_path) as c:
        u = ucc_compile_ut99(c, "UscHelloUT",
                             {"UscHelloUT.uc": "class UscHelloUT expands Object;\n"})
    assert len(u) > 64
    assert struct.unpack_from("<I", u, 0)[0] == _PKG_MAGIC


@pytest.mark.integration
@pytest.mark.skipif(not (_docker_up() and _substrate_present()),
                    reason="needs a live docker daemon and the fetched UT99 substrate")
def test_ipserver_roundtrips(tmp_path):
    """A code-only stock package decompiles then recompiles under UT99's own toolchain."""
    with ut99_container(state_dir=tmp_path) as c:
        sources = ucc_decompile_ut99(c, "IpServer")
        assert sources, "no classes decompiled from IpServer"
        u = ucc_compile_ut99(c, "IpServer", sources)
    assert len(u) > 64
    assert struct.unpack_from("<I", u, 0)[0] == _PKG_MAGIC
