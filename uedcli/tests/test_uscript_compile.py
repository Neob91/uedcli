"""`uscript.compile` byte-parity: compiling a declaration-only class reproduces UCC's `.u` exactly.

The oracle is `uscript.gate.gate` against a committed UCC golden. Ordering (name/import order) needs
the engine global-index tie-break table, which isn't available yet, so the strict comparison feeds
`compile_package` the golden's own (names, imports, exports) order via `order_override`; every OTHER
byte — bodies, flags, CRC, defaults, name flags — must then match with nothing masked but the GUID.
"""
from __future__ import annotations

from pathlib import Path

from uedcli.upackage import load_package
from uedcli.uscript.compile import compile_package
from uedcli.uscript.env import InstallEnv
from uedcli.uscript.gate import gate
from uedcli.uscript.serialize import serialize

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "uscript"
_UED22 = str(Path(__file__).resolve().parents[2] / "uned" / "UED22")

# class name -> the source UCC compiled the committed golden from (line endings normalised by the
# compiler; the source's trailing newline is preserved into ScriptText).
_SOURCES = {
    "UscHello": "class UscHello expands Object;\n",
    "UscVars": ("class UscVars expands Object;\n\n"
                "var int Alpha;\n"
                "var float Beta;\n"
                "var string Gamma;\n\n"
                "defaultproperties\n{\n"
                "     Alpha=7\n"
                "     Beta=1.500000\n"
                "}\n"),
    # Names deliberately NOT stock engine names: a name already in UED22's boot global name pool
    # (e.g. `Tag`, an Actor property) carries an extra 0x04000000 name-table flag the local flag
    # scheme can't derive without the engine's global name-flag table (same gap as import ORDER).
    "UscBB": ("class UscBB expands Object;\n\n"
              "var byte Bode;\n"
              "var bool Blip;\n"
              "var name Naym;\n\n"
              "defaultproperties\n{\n"
              "     Bode=3\n"
              "     Blip=True\n"
              "     Naym=Wobbl\n"
              "}\n"),
}


# A whole class of functions: empty body, bare `return`, int/bool returns, a param+local, a two-param
# int add, a native `Log` call, an int comparison. Exercises the UFunction export shell, the
# params→ReturnValue→locals Children chain, per-function CPF role flags, FunctionFlags, Line/TextPos,
# and byte-exact script lowering. Compiled by UCC into the committed `UscFn.u` golden.
_USC_FN_SRC = (
    "class UscFn expands Object;\n"
    "\n"
    "function F1() {}\n"
    "function F2() { return; }\n"
    "function int F3() { return 5; }\n"
    "function F4() { local int x; x = 3; }\n"
    "function int F5(int a, int b) { return a + b; }\n"
    "function F6() { Log(\"hi\"); }\n"
    "function bool F7(int a) { return a > 2; }\n"
)


def _env() -> InstallEnv:
    return InstallEnv([_UED22])


def _golden_orders(pkg) -> tuple[list[str], list[str], list[tuple[str, tuple[str, ...]]]]:
    """(names, imports, export_rows) read straight from a decoded golden. Each export row is
    (leaf name, outer-chain outermost->immediate) — the chain disambiguates duplicate names functions
    introduce (a param `A` of `F5` vs of `F7`, three `ReturnValue`s, …); empty for the class itself."""
    names = list(pkg.names)
    imports = [pkg.names[on] for (_cp, _cn, _pi, on) in pkg.imports]

    def chain(e):
        out, outer = [], e["outer"]
        while outer > 0:
            out.append(pkg.names[pkg.exports[outer - 1]["nm"]])
            outer = pkg.exports[outer - 1]["outer"]
        return tuple(reversed(out))
    exports = [(pkg.names[e["nm"]], chain(e)) for e in pkg.exports]
    return names, imports, exports


def _compile_with_golden_order(class_name: str) -> tuple[bytes, bytes]:
    golden = (_FIXTURES / f"{class_name}.u").read_bytes()
    pkg = load_package(str(_FIXTURES / f"{class_name}.u"))
    mine = serialize(compile_package(_SOURCES[class_name], _env(),
                                     order_override=_golden_orders(pkg)))
    return mine, golden


def _check(class_name: str) -> None:
    mine, golden = _compile_with_golden_order(class_name)
    result = gate(mine, golden)
    assert result.passed, f"{class_name}: " + " | ".join(result.messages)


def test_usc_hello_byte_exact():
    _check("UscHello")


def test_usc_vars_byte_exact():
    """int/float/string vars + `defaultproperties{Alpha=7 Beta=1.5}` (Gamma defaults to \"\")."""
    _check("UscVars")


def test_usc_bb_byte_exact():
    """byte/bool/name vars + defaults (Bode=3, Blip=True, Naym=Wobbl — a name-typed default)."""
    _check("UscBB")


def test_autonomous_byte_exact():
    """Compile byte-exact with NO `order_override`: a provisional compile is decoded and re-emitted in
    UCC's real name/import/export order (`reorder.true_order` — the runtime-dumped global index +
    faithful qsort, with value-only names — a package self-ref, a defaultproperties value — gathered
    at their real registration point per `ordering._gather_names`/`late_name_refs`), and FName case
    comes from the dumped pool. Covers scalar classes, a function class (UscFn), and a 21-function
    class with a stock-colliding member name (UscW, `Add`) — its name-table flags match too, so the
    engine boot-pool bit is not actually underivable, just was masked by the gather-order bug."""
    srcs = {**_SOURCES, "UscFn": _USC_FN_SRC, "UscW": (_FIXTURES / "UscW.uc").read_text()}
    for class_name in ("UscHello", "UscVars", "UscBB", "UscFn", "UscW"):
        golden = (_FIXTURES / f"{class_name}.u").read_bytes()
        mine = serialize(compile_package(srcs[class_name], _env()))   # no override
        result = gate(mine, golden)
        assert result.passed, f"{class_name}: " + " | ".join(result.messages)


def test_usc_fn_byte_exact():
    """A whole class of functions (F1-F7) compiles byte-exact: UFunction shells, child properties
    (params/ReturnValue/locals), FunctionFlags, Line/TextPos, and the lowered scripts."""
    golden = (_FIXTURES / "UscFn.u").read_bytes()
    pkg = load_package(str(_FIXTURES / "UscFn.u"))
    mine = serialize(compile_package(_USC_FN_SRC, _env(), order_override=_golden_orders(pkg)))
    result = gate(mine, golden)
    assert result.passed, "UscFn: " + " | ".join(result.messages)


def test_export_order_matches_golden_without_override():
    """`order_package` alone (no global-index table) already reproduces UCC's EXPORT order; only
    name/import within-tier order needs the tie-break table. Documents that gap boundary."""
    for class_name, pkg in ((c, load_package(str(_FIXTURES / f"{c}.u"))) for c in _SOURCES):
        _names, _imports, golden_exports = _golden_orders(pkg)
        auto = compile_package(_SOURCES[class_name], _env())
        got = [auto.names[e.name].text for e in auto.exports]
        assert got == [name for name, _outer in golden_exports], f"{class_name}: {got}"
