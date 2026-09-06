"""Tests for the UnrealScript parser (`uedcli.uscript.parser`).

Two layers:

- Unit tests over inline snippets pin the tricky grammar corners (operators as function names, nested
  `array<class<X>>`, `string[N]`, defaultproperties struct literals, states with labels, the Deus Ex
  `array<T,N>` form, inline enums, unary `+`, assignment-as-expression, empty default values, the
  `intrinsic`/`native` synonym). These need no docker.
- An integration test decompiles a spread of stock packages through UCC (`reference.py`) and asserts
  every exported class parses without `ParseError`. It gates on docker + the UED22 substrate exactly
  like `test_uscript_reference.py`, so it skips cleanly when they are absent.

Run with capture off and a repo-local TMPDIR (the shared /tmp crashes pytest capture on this host):
    mkdir -p _scratch/pttmp-parser
    TMPDIR=$PWD/_scratch/pttmp-parser .venv/bin/python -m pytest -p no:cacheprovider \
        -o cache_dir=_scratch/pttmp-parser/pc -s uedcli/tests/test_uscript_parser.py -q
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from uedcli.uscript.ast import ConstDecl, EnumDecl, StructDecl, VarDecl
from uedcli.uscript.parser import ParseError, parse

_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"


# ── unit tests: header ──────────────────────────────────────────────────────
def test_header_extends_and_modifiers():
    cd = parse("class Foo extends Bar native config(System) transient;\n")
    assert cd.name == "Foo"
    assert cd.super_name == "Bar"
    assert cd.modifiers == ("native", "config(System)", "transient")
    assert cd.source.startswith("class Foo")


def test_header_expands_and_within_and_guid():
    cd = parse("class Foo expands Object within Player guid(1,2,3,4) abstract;\n")
    assert cd.super_name == "Object"
    assert cd.within == "Player"
    assert "guid(1,2,3,4)" in cd.modifiers
    assert "abstract" in cd.modifiers


def test_unknown_modifier_preserved():
    cd = parse("class Foo extends Bar wibblefrobnicate;\n")
    assert "wibblefrobnicate" in cd.modifiers


def test_missing_class_keyword_errors():
    with pytest.raises(ParseError):
        parse("struct Foo {};\n")


def test_error_names_token_with_line_col():
    with pytest.raises(ParseError) as ei:
        parse("class Foo extends Bar\nfunction $$$;\n")
    assert "line" in str(ei.value) and "col" in str(ei.value)


# ── unit tests: members ─────────────────────────────────────────────────────
def _members(src: str):
    return parse(src).members


def test_const_enum_struct_var_order_preserved():
    src = (
        "class C extends Object;\n"
        "const MAX = 5;\n"
        "enum E { A, B, C };\n"
        "struct S { var int x; };\n"
        "var int a, b;\n"
    )
    m = _members(src)
    assert [type(x) for x in m] == [ConstDecl, EnumDecl, StructDecl, VarDecl]
    assert m[0].name == "MAX" and m[0].value.op == "intconst" and m[0].value.value == 5
    assert m[1].values == ("A", "B", "C")
    assert m[2].members[0].names == ("x",)
    assert m[3].names == ("a", "b")


def test_enum_trailing_comma_and_no_comma_mix():
    (e,) = [x for x in _members("class C;\nenum E { A, B, };\n") if isinstance(x, EnumDecl)]
    assert e.values == ("A", "B")


def test_var_category_and_modifiers_and_static_dim():
    m = _members("class C;\nvar(Sound) private const sound s;\nvar int grid[8];\n")
    assert m[0].category == "Sound"
    assert m[0].modifiers == ("private", "const")
    assert m[1].array_dim == 8


def test_var_bare_category_is_empty_string():
    (v,) = _members("class C;\nvar() bool b;\n")
    assert v.category == ""


def test_static_dim_from_const_name():
    (v,) = _members("class C;\nvar int a[MAX_THINGS];\n")
    assert v.array_dim == "MAX_THINGS"


def test_nested_array_of_class():
    (v,) = _members("class C;\nvar array<class<Actor> > items;\n")
    t = v.type
    assert t.base == "array"
    assert t.inner.base == "class" and t.inner.meta_class == "Actor"


def test_array_of_class_closing_shift_token():
    # `>>` must split into two closing angle brackets.
    (v,) = _members("class C;\nvar array<class<Actor>> items;\n")
    assert v.type.inner.meta_class == "Actor"


def test_string_fixed_size():
    (v,) = _members("class C;\nvar string[32] label;\n")
    assert v.type.base == "string" and v.type.string_size == 32


def test_deusex_sized_array():
    (v,) = _members("class C;\nvar const array<actor,4> Touching;\n")
    assert v.type.base == "array" and v.type.inner.base == "actor" and v.type.array_size == 4


def test_intrinsic_is_native_synonym_var():
    (v,) = _members("class C;\nvar const intrinsic DynamicArray d;\n")
    assert "intrinsic" in v.modifiers and v.type.base == "DynamicArray"


def test_inline_enum_in_var_registers_member():
    m = _members("class C;\nvar() enum ELightType { LT_None, LT_Steady } LightType;\n")
    assert [type(x) for x in m] == [EnumDecl, VarDecl]
    assert m[0].values == ("LT_None", "LT_Steady")
    assert m[1].names == ("LightType",) and m[1].type.base == "ELightType"


def test_inline_enum_in_struct_member_is_hoisted():
    m = _members("class C;\nstruct S { var enum EFoo { A, B } f; };\n")
    structs = [x for x in m if isinstance(x, StructDecl)]
    enums = [x for x in m if isinstance(x, EnumDecl)]
    assert structs and structs[0].members[0].type.base == "EFoo"
    assert enums and enums[0].name == "EFoo" and enums[0].values == ("A", "B")  # not dropped


# ── unit tests: functions / operators ───────────────────────────────────────
def _funcs(src: str):
    return parse(src).functions


def test_native_indexed_function_no_body():
    (f,) = _funcs("class C;\nnative(1409) final function window NewChild(class nc, optional bool s);\n")
    assert f.name == "NewChild" and f.kind == "function"
    assert f.native_index == 1409
    assert set(f.modifiers) >= {"native", "final"}
    assert f.return_type.base == "window"
    assert f.has_body is False
    assert f.params[0].name == "nc" and f.params[0].type.base == "class"
    assert f.params[1].modifiers == ("optional",) and f.params[1].name == "s"


def test_intrinsic_indexed_function():
    (f,) = _funcs("class C;\nintrinsic(2054) final function float GetSoundLength( Sound aSound );\n")
    assert f.native_index == 2054 and f.return_type.base == "float"


def test_function_no_return_type():
    (f,) = _funcs("class C;\nfunction Destroy() { }\n")
    assert f.name == "Destroy" and f.return_type is None and f.has_body is True


def test_operator_symbolic_name_and_precedence():
    (f,) = _funcs("class C;\nnative(129) static final operator(24) bool == (Object A, Object B);\n")
    assert f.kind == "operator" and f.name == "==" and f.oper_precedence == 24
    assert f.return_type.base == "bool"


def test_preoperator_and_word_operator_name():
    fs = _funcs(
        "class C;\n"
        "native final preoperator bool ! (bool A);\n"
        "native(16) final operator(16) vector Cross (vector A, vector B);\n")
    assert fs[0].kind == "preoperator" and fs[0].name == "!"
    assert fs[1].kind == "operator" and fs[1].name == "Cross" and fs[1].return_type.base == "vector"


def test_out_coerce_default_params():
    (f,) = _funcs("class C;\nfunction F(out int x, coerce string s, optional int n) { }\n")
    assert f.params[0].modifiers == ("out",)
    assert f.params[1].modifiers == ("coerce",)
    assert f.params[2].modifiers == ("optional",)


def test_function_locals_and_body():
    src = (
        "class C;\n"
        "function F() {\n"
        "  local int i;\n"
        "  local color c;\n"
        "  i = 3;\n"
        "  return;\n"
        "}\n")
    (f,) = _funcs(src)
    assert [v.type.base for v in f.locals] == ["int", "color"]
    assert [s.kind for s in f.body] == ["assign", "return"]
    assert f.body[0].text == "="


# ── unit tests: statements / expressions ─────────────────────────────────────
def _body(func_src: str):
    return _funcs("class C;\nfunction F() {\n" + func_src + "\n}\n")[0].body


def test_if_elseif_else_chain():
    (s,) = _body("if (a > 1) x=1; else if (a > 0) x=2; else x=3;")
    assert s.kind == "if"
    conds = [c for c, _ in s.clauses]
    assert conds[0] is not None and conds[1] is not None and conds[2] is None


def test_for_while_do_switch():
    body = _body(
        "for (i=0; i<n; i++) Foo();\n"
        "while (b) Bar();\n"
        "do Baz(); until (c);\n"
        "switch (x) { case 1: y=1; break; default: y=0; }\n")
    kinds = [s.kind for s in body]
    assert kinds == ["for", "while", "do", "switch"]
    sw = body[3]
    assert sw.clauses[0][0].value == 1
    assert sw.clauses[-1][0] is None  # default arm


def test_assignment_as_expression_in_paren():
    (s,) = _body("if ((MsgTime -= Delta) <= 0.0) TextLines--;")
    assert s.kind == "if"
    paren = s.clauses[0][0].children[0]
    assert paren.op == "paren" and paren.children[0].op == "assign"
    assert paren.children[0].text == "-="


def test_unary_plus_and_call_args():
    (s,) = _body("BuildCube( +1, Breadth-WallThickness );")
    call = s.exprs[0]
    assert call.op == "call"
    assert call.children[1].op == "unary" and call.children[1].text == "+"
    assert call.children[2].op == "binary" and call.children[2].text == "-"


def test_operator_precedence_nesting():
    (s,) = _body("x = a + b * c;")
    rhs = s.exprs[1]
    assert rhs.op == "binary" and rhs.text == "+"
    assert rhs.children[1].op == "binary" and rhs.children[1].text == "*"


def test_word_operator_precedence_differs():
    # Dot binds like `*` (16, tighter than `+`); ClockwiseFrom is a comparison (24, looser than `+`).
    (s,) = _body("x = a Dot b + c;")
    assert s.exprs[1].text == "+" and s.exprs[1].children[0].text == "Dot"
    (s2,) = _body("y = a ClockwiseFrom b + c;")
    assert s2.exprs[1].text == "ClockwiseFrom" and s2.exprs[1].children[1].text == "+"


def test_member_call_index_chain():
    (s,) = _body("y = obj.list[3].Method(1);")
    call = s.exprs[1]
    assert call.op == "call"
    member = call.children[0]
    assert member.op == "member" and member.text == "Method"
    assert member.children[0].op == "index"


def test_super_and_self_and_none():
    body = _body("Super.PreRender(Canvas);\nx = Self;\ny = None;")
    assert body[0].exprs[0].op == "call"
    assert body[1].exprs[1].op == "self"
    assert body[2].exprs[1].op == "noneconst"


def test_object_literal_expression():
    (s,) = _body("t = Texture'Package.Group.Name';")
    obj = s.exprs[1]
    assert obj.op == "objref" and obj.text == "Texture" and obj.value == "Package.Group.Name"


def test_label_and_goto_in_body():
    body = _body("goto Retry;\nRetry:\nFoo();")
    assert body[0].kind == "goto" and body[0].text == "Retry"
    assert body[1].kind == "label" and body[1].names == ("Retry",)


def test_goto_name_literal_normalized():
    (s,) = _body("goto 'Begin';")
    assert s.kind == "goto" and s.text == "Begin"  # matches a `label` Stmt's spelling


def test_stop_keyword_vs_call():
    body = _body("Stop();\nstop;")
    assert body[0].kind == "expr" and body[0].exprs[0].op == "call"
    assert body[1].kind == "stop"


def test_foreach_statement():
    (s,) = _body("foreach AllActors(class'Engine.Pawn', P) P.Died();")
    assert s.kind == "foreach"
    assert s.exprs[0].op == "call"
    assert s.body[0].kind == "expr"


# ── unit tests: states / replication / defaults ─────────────────────────────
def test_state_with_ignores_funcs_and_labels():
    src = (
        "class C extends Actor;\n"
        "auto state Waiting extends Idle {\n"
        "  ignores Touch, UnTouch;\n"
        "  function Foo() { }\n"
        "Begin:\n"
        "  Sleep(1.0);\n"
        "  goto 'Begin';\n"
        "}\n")
    (st,) = parse(src).states
    assert st.name == "Waiting" and st.base == "Idle" and "auto" in st.modifiers
    assert st.ignores == ("Touch", "UnTouch")
    assert [f.name for f in st.funcs] == ["Foo"]
    assert st.body[0].kind == "label" and st.body[0].names == ("Begin",)


def test_replication_block():
    src = (
        "class C extends Actor;\n"
        "replication {\n"
        "  reliable if (Role == ROLE_Authority) health, ammo;\n"
        "  unreliable if (bNet) pos;\n"
        "}\n")
    rep = parse(src).replication
    assert rep is not None
    assert rep.entries[0][0] is True and rep.entries[0][2] == ("health", "ammo")
    assert rep.entries[1][0] is False and rep.entries[1][2] == ("pos",)


def test_empty_replication_block():
    rep = parse("class C extends Actor;\nreplication {\n}\n").replication
    assert rep is not None and rep.entries == ()


def test_defaultproperties_scalars_struct_and_array_index():
    src = (
        "class C extends Object;\n"
        "defaultproperties\n"
        "{\n"
        "     Name=\"hi\"\n"
        "     Count=-5\n"
        "     Flag=True\n"
        "     Owner=None\n"
        "     textColor=(R=1,G=2,B=3,A=0)\n"
        "     actorList(2)=(Actor=None,refCount=0)\n"
        "     Skin=Texture'DeusEx.Skins.Foo'\n"
        "}\n")
    dp = {p.name: p for p in parse(src).default_props}
    assert dp["Name"].value.op == "stringconst" and dp["Name"].value.value == "hi"
    assert dp["Count"].value.value == -5
    assert dp["Flag"].value.op == "boolconst" and dp["Flag"].value.value is True
    assert dp["Owner"].value.op == "noneconst"
    tc = dp["textColor"].value
    assert tc.op == "struct" and tc.children[0].text == "R" and tc.children[0].children[0].value == 1
    assert dp["actorList"].array_index == 2 and dp["actorList"].value.op == "struct"
    assert dp["Skin"].value.op == "objref" and dp["Skin"].value.value == "DeusEx.Skins.Foo"


def test_defaultproperties_empty_value():
    src = "class C;\ndefaultproperties\n{\n     FramePtr=\n     Scale=1\n}\n"
    dp = {p.name: p for p in parse(src).default_props}
    assert dp["FramePtr"].value.op == "empty"
    assert dp["Scale"].value.value == 1


def test_exec_directives_collected():
    cd = parse("class C;\n#exec Texture Import File=Foo.pcx Name=Bar\nvar int x;\n")
    assert cd.exec_directives == ("Texture Import File=Foo.pcx Name=Bar",)


def test_cpptext_captured_raw():
    cd = parse("class C;\ncpptext\n{\n    INT Foo() { return 1; }\n}\nvar int x;\n")
    assert cd.cpptext is not None and "INT Foo()" in cd.cpptext
    assert any(getattr(m, "names", None) == ("x",) for m in cd.members)


def test_source_is_verbatim():
    src = "class C extends Object;\r\nvar int x;\r\n"
    assert parse(src).source == src


# ── integration: parse the real decompiled corpus ───────────────────────────
def _docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=30).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


_INTEGRATION_PKGS = ["core", "Extension", "ConSys", "uwindow", "Engine", "editor"]


@pytest.mark.integration
@pytest.mark.skipif(
    not (_docker_up() and (_UED22 / "UCC.exe").is_file()),
    reason="needs a live docker daemon and the committed UED22 substrate (UCC.exe)")
def test_parses_decompiled_stock_packages(tmp_path):
    """Decompile a script-heavy spread and assert every exported class parses, keeping key facts."""
    from uedcli.uscript.reference import ucc_container, ucc_decompile

    parsed = 0
    seen_super = seen_func = seen_operator = seen_state = False
    with ucc_container(state_dir=tmp_path) as container:
        for pkg in _INTEGRATION_PKGS:
            sources = ucc_decompile(container, pkg)
            assert sources, f"no classes decompiled for {pkg!r}"
            for filename, src in sources.items():
                try:
                    cd = parse(src)
                except ParseError as e:
                    pytest.fail(f"{pkg}/{filename} failed to parse: {e}")
                assert cd.name, f"{pkg}/{filename}: empty class name"
                assert cd.source == src
                parsed += 1
                seen_super = seen_super or cd.super_name is not None
                seen_func = seen_func or bool(cd.functions)
                seen_operator = seen_operator or any(
                    f.kind in ("operator", "preoperator", "postoperator") for f in cd.functions)
                seen_state = seen_state or bool(cd.states)
    assert parsed > 200, f"expected a broad corpus, only parsed {parsed}"
    assert seen_super and seen_func and seen_operator and seen_state
