"""Whole-package compile (`uscript.compile.compile_package_dir`): many `.uc` -> ONE `.u` with shared
name/import/export tables, byte-exact vs UCC under the identity/permutation gate (`gate.perm_gate`).

The offline tests run `compile_package_dir` and `perm_gate` against committed UCC goldens (built by
`UCC make`, see `test_goldens_match_ucc` for the recipe). They pin:
  - same-package super: `Derived expands Base` -> Base is an EXPORT ref, not an import (`pkg_TwoCls`);
  - same-package super CHAIN `A<-B<-C` with virtual calls up the chain (`pkg_ChainPkg`);
  - a non-Core super (`BrushBuilder` in Editor) across two classes: the shared Editor import and the
    per-class `[<pkg>, Editor, Core]` PackageImports (`pkg_TwoBB`);
  - two SIBLING (non-super) classes that reference each other MUTUALLY — A holds a member typed B and
    calls a B method, B holds a member typed A and calls an A method (`pkg_Mutual`; see
    `_prepass_signatures`/`_PkgSigGraph` in `compile.py` for the two-pass signature resolution this
    needs). `perm_gate` only, not the strict byte gate — the residual is a same-package name-table
    qsort-TIE permutation, the same open class of issue `ExtendedBuilders` hits (see
    `USCRIPT-COMPILER.md`), not specific to the mutual-reference mechanism itself.

Six more fixtures (2026-09-13) each pin one gap found compiling the real `UWeb` package
(`USCRIPT-COMPILER.md`'s "Real UWeb" entry) — every one verified against a live UED22 `UCC.exe` build,
not just the real UWeb corpus attempt:
  - `pkg_SamePkgMisc`: a same-package class LITERAL (`class'SPBase'`/`new(...) class'SPBase'`), a
    `class<T>` property typed to a sibling, a same-package `Super` call resolving to an EXPORT, and a
    member sharing its name with an unrelated sibling class (`var SPFoo SPFoo;` — a cast `SPFoo(x)`
    must resolve to the CLASS, a bare `SPFoo` read/write to the MEMBER).
  - `pkg_PoolCaseDedup`: the SCARIEST fix — two classes each declare a param/local differing only in
    case (`S` / `s`); `pool_case` can re-spell them onto the SAME final name AFTER the gather's own
    case-sensitive dedup already treated them as distinct, silently shifting every export's baked-in
    name-table index by one from the collision point on (`compile._pool_cased_dedup`).
  - `pkg_InheritedObjMember`: reading an INHERITED object-typed member (`Actor.Level`) never declared
    locally.
  - `pkg_GlobalEnumTag`: an unqualified enum tag (`GetKind_B`) resolved through a SIBLING class with
    no inheritance relation to the enum's declaring class — enum tags are globally scoped in real UCC.
  - `pkg_MiscFlags`: `CPF_Native` on a `native` var (ONLY when the owning class is itself native — see
    `test_cpf_native_requires_native_class`), a function param's and a local's static-array size
    (`byte B[8]`/`local byte Buf[4]`), and a non-native body-less function declaration (`function
    Setup();`) compiling as an empty body (`Return(Nothing)`, not a native-style zero-script stub).
  - `pkg_NoSpuriousPkgImport`: a property TYPE reference to another package (`var LevelInfo Level;`,
    Engine) must NOT add that package to `PackageImports` — only the super chain's transitive deps do.
  - `pkg_CPFNativeProbe`: `CPF_Native` needs BOTH the var's own `native` keyword AND the owning class
    itself being `native` — a `native` var in a non-native class carries no CPF bit.

`pkg_DepOrderProbe` (2026-09-13) pins the real `Dependencies`-array counting rule found finishing the
real `UWeb` corpus attempt: one entry per syntactic Context occurrence (undeduped), gathered per-
function forward but ACROSS functions in REVERSE declaration order (`compile._build_callables`).

`test_goldens_match_ucc` (docker-gated) rebuilds the goldens with UCC and re-gates, so the committed
fixtures can't silently drift from the compiler.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.compile import compile_package_dir
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import perm_gate
from uedcli.uscript.serialize import serialize

_FIX = Path(__file__).resolve().parent / "fixtures" / "uscript"
_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

# package name -> {filename: source}. The source UCC compiled each committed golden from.
_PACKAGES: dict[str, dict[str, str]] = {
    "TwoCls": {
        "Base.uc": "class Base expands Object;\n\nvar int N;\n\nfunction int Get() { return N; }\n",
        "Derived.uc": "class Derived expands Base;\n\nfunction int GetPlus() { return Get() + 1; }\n",
    },
    "ChainPkg": {
        "A.uc": "class A expands Object;\n\nvar int N;\n\nfunction int Get() { return N; }\n",
        "B.uc": "class B expands A;\n\nfunction int GetB() { return Get() + 1; }\n",
        "C.uc": "class C expands B;\n\nfunction int GetC() { return GetB() * 2; }\n",
    },
    "TwoBB": {
        "BBAlpha.uc": "class BBAlpha expands BrushBuilder;\n\nvar int Alpha;\n",
        "BBBeta.uc": "class BBBeta expands BrushBuilder;\n\nvar float Beta;\n",
    },
    "Mutual": {
        "MutualA.uc": (
            "class MutualA expands Object;\n\n"
            "var MutualB Partner;\n"
            "var int Value;\n\n"
            "function int Ping()\n{\n    return Partner.Pong(Self);\n}\n\n"
            "function int GetValue()\n{\n    return Value;\n}\n"),
        "MutualB.uc": (
            "class MutualB expands Object;\n\n"
            "var MutualA Partner;\n\n"
            "function int Pong(MutualA a)\n{\n    Partner = a;\n    return a.GetValue();\n}\n"),
    },
    "SamePkgMisc": {
        "SPBase.uc": (
            "class SPBase expands Object;\n\n"
            "function string Greet()\n{\n    return \"base\";\n}\n"),
        "SPSub.uc": (
            "class SPSub expands SPBase;\n\n"
            "function string Greet()\n{\n    return \"sub:\" $ Super.Greet();\n}\n"),
        "SPFoo.uc": (
            "class SPFoo expands Object;\n\n"
            "function string Tag()\n{\n    return \"foo\";\n}\n"),
        "SPUser.uc": (
            "class SPUser expands Object;\n\n"
            "var SPFoo SPFoo;\n"
            "var Object Generic;\n"
            "var class<SPBase> BaseClass;\n\n"
            "function DoIt()\n{\n"
            "    local SPBase b;\n"
            "    b = new(None) class'SPBase';\n"
            "    BaseClass = class'SPBase';\n"
            "    SPFoo = SPFoo(Generic);\n"
            "}\n"),
    },
    "PoolCaseDedup": {
        "PCDOne.uc": (
            "class PCDOne expands Object;\n\n"
            "function Foo(string S)\n{\n    Log(S);\n}\n"),
        "PCDTwo.uc": (
            "class PCDTwo expands Object;\n\n"
            "function Bar()\n{\n    local string s;\n    s = \"x\";\n    Log(s);\n}\n"),
    },
    "InheritedObjMember": {
        "IOMActor.uc": (
            "class IOMActor expands Actor;\n\n"
            "function LevelInfo GetLevel()\n{\n    return Level;\n}\n"),
    },
    "GlobalEnumTag": {
        "GETHolder.uc": (
            "class GETHolder expands Object;\n\n"
            "enum EGetKind\n{\n    GetKind_A,\n    GetKind_B\n};\n\n"
            "var EGetKind Kind;\n"),
        "GETUser.uc": (
            "class GETUser expands Object;\n\n"
            "var GETHolder Holder;\n\n"
            "function UseTag()\n{\n    Holder.Kind = GetKind_B;\n}\n"),
    },
    "MiscFlags": {
        "MFOne.uc": (
            "class MFOne expands Object;\n\n"
            "var private native const int Flags[3];\n\n"
            "function DoWork(byte B[8])\n{\n"
            "    local byte Buf[4];\n"
            "    Buf[0] = B[0];\n"
            "}\n\n"
            "function Setup();\n\n"
            "defaultproperties\n{\n}\n"),
    },
    "NoSpuriousPkgImport": {
        "NSPIOne.uc": (
            "class NSPIOne expands Object;\n\n"
            "var LevelInfo Level;\n\n"
            "defaultproperties\n{\n}\n"),
    },
    "DepOrderProbe": {
        # Pins the real `Dependencies`-array counting rule (RE'd 2026-09-13 against real UWeb, see
        # `USCRIPT-COMPILER.md`'s UWeb entry / `compile-model.md`'s "Cross-class Dependency entries"):
        # ONE entry per syntactic Context occurrence (not deduped by class), in source-textual order
        # within a function (an outer Context's own entry precedes one nested in its call's own
        # arguments), but functions/states are gathered in REVERSE declaration order across the class
        # (the same reversal `_class_chain` already applies to the Children chain). `Repeat` (declared
        # SECOND) repeats `T.A()` three times undeduped; `NestedCall` (declared FIRST) proves
        # outer-before-inner (`W.Wrap(` records `Widget` before its own arg `T.A()` records `Thing`).
        # Expected Dependencies: self, super, then Thing,Thing,Thing (Repeat) before Widget,Thing
        # (NestedCall) -- `Repeat` gathers AFTER `NestedCall` despite being declared after it in
        # source.
        "Thing.uc": "class Thing expands Object;\n\nfunction int A()\n{\n    return 1;\n}\n",
        "Widget.uc": "class Widget expands Object;\n\nfunction int Wrap(int X)\n{\n    return X;\n}\n",
        "DepOrderProbe.uc": (
            "class DepOrderProbe expands Object;\n\n"
            "function int NestedCall(Widget W, Thing T)\n{\n    return W.Wrap(T.A());\n}\n\n"
            "function int Repeat(Thing T)\n{\n    return T.A() + T.A() + T.A();\n}\n"),
    },
    "CPFNativeProbe": {
        # Each class declares ONLY the one native var under test (no unset PLAIN sibling) -- a
        # native class with an unset plain property hits a SEPARATE, pre-existing defaults-emission
        # bug unrelated to CPF_Native (see
        # dev/docs/board/inbox/native-class-lone-plain-var-gets-a-spurious-zero-default/).
        "CPFNativeClassNativeVar.uc": (
            "class CPFNativeClassNativeVar expands Object native noexport;\n\n"
            "var native int NativeVar;\n"),
        "CPFPlainClassNativeVar.uc": (
            "class CPFPlainClassNativeVar expands Object;\n\n"
            "var native int NativeVar;\n"),
    },
}


def _env() -> InstallEnv:
    return InstallEnv([str(_UED22)])


def _compile(name: str) -> bytes:
    return serialize(compile_package_dir(_PACKAGES[name], _env(), package_name=name))


def _check(name: str) -> None:
    golden = (_FIX / f"pkg_{name}.u").read_bytes()
    r = perm_gate(_compile(name), golden)
    assert r.passed, f"{name}: " + " | ".join(r.messages)


def test_two_class_same_package_super():
    """`Derived expands Base` (same package) + a cross-class virtual call `Get()`. Base is an export
    ref (SuperField/Dependency), not an import."""
    _check("TwoCls")


def test_three_class_chain():
    """A 3-class same-package chain `A<-B<-C` with virtual calls up the chain — exercises the
    incremental in-package graph (each class sees its already-compiled supers)."""
    _check("ChainPkg")


def test_two_class_noncore_super():
    """Two classes expanding `BrushBuilder` (Editor): one shared Editor import, and each class's
    PackageImports = `[TwoBB, Editor, Core]`."""
    _check("TwoBB")


def test_mutual_same_package_classes():
    """Two SIBLING classes (no inheritance relation) that reference each other MUTUALLY: `MutualA`
    holds a `MutualB`-typed member and calls a `MutualB` method, `MutualB` holds a `MutualA`-typed
    member/param and calls a `MutualA` method. Neither can be fully compiled before the other under a
    single-pass, build-order-dependent resolution scheme — this is the two-pass signature-graph fix
    (`_prepass_signatures`/`_PkgSigGraph`)."""
    _check("Mutual")


def test_same_package_class_literal_super_and_name_collision():
    """A same-package class LITERAL (`class'SPBase'`/`new(...) class'SPBase'`), a `class<T>` property
    typed to a sibling, `Super.Greet()` resolving to an in-package EXPORT (not an import), and a
    member sharing its name with an unrelated sibling class (`var SPFoo SPFoo;` — casting `SPFoo(x)`
    must resolve to the CLASS, a bare `SPFoo` read/write to the MEMBER, never confused with each
    other) — all found compiling the real `UWeb` package (`WebServer`/`WebRequest`/`HelloWeb`)."""
    _check("SamePkgMisc")


def test_pool_case_dedup_does_not_corrupt_name_indices():
    """Two classes each declare a param/local differing only in case (`S` in `PCDOne.Foo`, `s` in
    `PCDTwo.Bar`) — the gather's dedup is case-SENSITIVE on the source spelling, so both survive as
    distinct entries; `pool_case` can then re-spell one onto the other's exact final text (the boot
    pool already has `S`), which `serialize.NameTable`'s dedup (case-sensitive on the FINAL spelling)
    then collapses to one slot. Without re-deduping post-`pool_case` (`compile._pool_cased_dedup`),
    every export's baked-in name-table index after the collision point silently pointed at the WRONG
    name — found chasing an unrelated-looking symptom while compiling the real `WebConnection`/
    `WebServer` (UWeb)."""
    _check("PoolCaseDedup")


def test_inherited_object_typed_member():
    """Reading an inherited OBJECT-typed member never declared locally (`Actor.Level`, type
    `LevelInfo`) — `_register_member_var_imports` only handled `_SCALAR_KINDS` before; an import table
    row needs no type-tail, so any type down to its UProperty subclass (`ObjectProperty`/
    `ClassProperty`/`StructProperty`) is enough (`_member_import_prop_class`)."""
    _check("InheritedObjMember")


def test_enum_tag_globally_scoped_across_unrelated_classes():
    """An unqualified enum tag (`GetKind_B`, declared on `GETHolder.EGetKind`) resolves through
    `GETUser`, a SIBLING class with NO inheritance relation to `GETHolder` — enum tags are globally
    scoped in real UCC (`ClassGraph.enum_ordinal` already scanned every ON-DISK package's enums
    regardless of class; `_PkgSigGraph.enum_ordinal` extends that scan to this in-progress package's
    own classes, which have no compiled bytes yet for the disk-based scan to see)."""
    _check("GlobalEnumTag")


def test_misc_native_and_array_and_bodyless_function_flags():
    """`CPF_Native` on a `native` var (only when the owning class is ALSO native — see
    `test_cpf_native_requires_native_class`), a function param's and a local's static-array size
    (`byte B[8]`, `local byte Buf[4]` — the parser previously parsed and discarded a param's size, and
    `_add_func_prop` hardcoded `array_dim=1` for every param/local), and a non-native body-less
    function declaration (`function Setup();`, meant to be overridden) compiling as an EMPTY body —
    `Return(Nothing)`, not a native-style zero-script stub."""
    _check("MiscFlags")


def test_property_type_reference_does_not_pollute_package_imports():
    """A property TYPE reference to another package (`var LevelInfo Level;`, Engine) gets its own
    IMPORT table entry but must NOT add that package to `PackageImports` — only the super chain's
    transitive package deps do. Reproduces on 4 of `UWeb`'s 6 non-trivial classes (`HelloWeb`/
    `ImageServer`/`WebApplication`/`WebResponse`, each with an object/class-typed property whose
    package isn't otherwise needed) before the fix."""
    _check("NoSpuriousPkgImport")


def test_dependencies_array_one_entry_per_context_occurrence():
    """`Dependencies` (deep=0) gets ONE entry per syntactic Context occurrence, undeduped, gathered
    per-function in source-textual order but ACROSS functions in REVERSE declaration order (RE'd
    2026-09-13 against real UWeb's `HelloWeb`/`WebConnection`/`WebResponse` — see `USCRIPT-COMPILER.md`
    and `compile-model.md`'s "Cross-class Dependency entries"). See `_PACKAGES["DepOrderProbe"]` for
    the exact mechanism each part of this fixture proves."""
    _check("DepOrderProbe")


def test_cpf_native_requires_native_class():
    """`CPF_Native` (`0x00001000`) needs BOTH the var's own `native` keyword AND the owning class
    itself being `native` — a `native` var in a NON-native class carries no CPF bit (measured live:
    the previous fix mapped the `native`/`intrinsic` var modifier straight to `CPF_NATIVE`
    unconditionally, which is wrong whenever the class itself isn't native)."""
    _check("CPFNativeProbe")


def test_perm_gate_catches_wrong_body():
    """A genuine divergence FAILS: compiling `Base.Get` as `return N + 1` must not pass against the
    `return N` golden."""
    pkg = dict(_PACKAGES["TwoCls"])
    pkg["Base.uc"] = pkg["Base.uc"].replace("return N;", "return N + 1;")
    mine = serialize(compile_package_dir(pkg, _env(), package_name="TwoCls"))
    r = perm_gate(mine, (_FIX / "pkg_TwoCls.u").read_bytes())
    assert not r.passed
    assert any("BODY" in m for m in r.messages)


def test_inherited_default_now_compiles():
    """Setting an INHERITED member in `defaultproperties` (a `BrushBuilder` subclass's
    `BitmapFilename`, inherited from `BrushBuilder`) now compiles — the type is resolved across the
    super chain and the override tag emitted. (Was a NotImplementedError frontier; fixed alongside
    the brush-builder corpus work — ExtendedBuilders exercises it end-to-end.)"""
    src = ("class Foo expands BrushBuilder;\n\n"
           "defaultproperties\n{\n     BitmapFilename=\"x\"\n}\n")
    out = serialize(compile_package_dir({"Foo.uc": src}, _env(), package_name="Foo"))
    assert out[:4] == b"\xc1\x83\x2a\x9e"   # a valid UE1 package, no exception


# ── docker-gated: rebuild the goldens with UCC and re-gate (keeps the fixtures honest) ──────────────
def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


@pytest.mark.integration
@pytest.mark.skipif(not (_docker_up() and (_UED22 / "UCC.exe").is_file()),
                    reason="needs a live docker daemon and the committed UED22 substrate (UCC.exe)")
@pytest.mark.parametrize("name", list(_PACKAGES))
def test_goldens_match_ucc(tmp_path, name):
    """`perm_gate(compile_package_dir(...), UCC.make(...))` is byte-exact for a FRESH UCC build — and
    the committed golden matches that fresh build. Recipe: `UCC make` over `<pkg>/Classes/*.uc`."""
    from uedcli.uscript.reference import ucc_compile, ucc_container
    with ucc_container(state_dir=tmp_path) as container:
        fresh = ucc_compile(container, name, _PACKAGES[name])
    assert perm_gate(_compile(name), fresh).passed, f"{name}: compile != fresh UCC"
    assert perm_gate((_FIX / f"pkg_{name}.u").read_bytes(), fresh).passed, \
        f"{name}: committed golden != fresh UCC (regenerate the fixture)"
