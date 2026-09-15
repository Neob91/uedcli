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
            ("UscNetConnectionProbe", 5)]

# Extra stock EditPackages a fixture's super chain needs loaded (`_edit_packages_upto`'s
# content-safe base only covers Core/Engine/Editor) — only needed for the DOCKER-gated rebuild.
_DEPS: dict[str, tuple[str, ...]] = {"UscInheritFinal": ("UWindow",), "UWeb": ("IpDrv",),
                                     "UscIpAddrProbe": ("IpDrv",), "ASPMutator": ("Botpack",),
                                     "UTServerAdmin": ("UWindow", "IpDrv", "Botpack")}


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
