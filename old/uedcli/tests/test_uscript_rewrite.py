import textwrap

import pytest

from uedcli.uscript_rewrite import (parse_class, render_stub, rewrite_imports,
                                    parse_meshmap_scales, reconcile_meshmap_scale,
                                    rehome_self_refs, flag_cross_package_refs,
                                    read_uc, rename_group_prefixed_pcx, UScriptParseError)


def test_it_strips_function_and_state_bodies_from_the_stub():
    # Arrange — a class carrying a function body AND a state body around the keep-set.
    src = textwrap.dedent("""\
        class Widget extends Actor;

        var int Count;

        function int Add(int a, int b)
        {
            return a + b;
        }

        state Active
        {
            function Tick() { Count++; }
        }

        defaultproperties
        {
            Count=3
        }
    """)

    # Act
    stub = render_stub(parse_class(src))

    # Assert — keep-set survives, every body construct is gone.
    assert "class Widget extends Actor;" in stub
    assert "var int Count;" in stub
    assert "Count=3" in stub
    assert "Add" not in stub
    assert "return a + b" not in stub
    assert "Active" not in stub
    assert "Count++" not in stub


def test_it_keeps_and_round_trips_exec_directives():
    # Arrange
    src = textwrap.dedent(r"""
        class Ammo extends Pickup;

        #exec MESH IMPORT MESH=GEPAmmo ANIVFILE=Models\gep_ammo_a.3d DATAFILE=Models\gep_ammo_d.3d
        #exec MESHMAP SCALE MESHMAP=GEPAmmo X=0.1 Y=0.1 Z=0.2
        #exec TEXTURE IMPORT NAME=GEPAmmoTex1 GROUP=Skins

        function PostBeginPlay()
        {
            Super.PostBeginPlay();
        }

        defaultproperties
        {
        }
    """)

    # Act
    stub = render_stub(parse_class(src))

    # Assert — every #exec survives; the function body does not.
    assert "#exec MESH IMPORT MESH=GEPAmmo ANIVFILE=Models\\gep_ammo_a.3d" in stub
    assert "#exec MESHMAP SCALE MESHMAP=GEPAmmo X=0.1 Y=0.1 Z=0.2" in stub
    assert "#exec TEXTURE IMPORT NAME=GEPAmmoTex1 GROUP=Skins" in stub
    assert "PostBeginPlay" not in stub


def test_it_keeps_enums_and_structs_and_drops_functions_between_them():
    # Arrange — enum, struct (with inner vars + braces), a function, then a var.
    src = textwrap.dedent("""
        class Thing extends Object;

        enum EState { ES_Idle, ES_Run };

        struct Pair { var int A; var int B; };

        function Helper() { local int x; x = 1; }

        var EState State;

        defaultproperties
        {
        }
    """)

    # Act
    stub = render_stub(parse_class(src))

    # Assert — enum/struct/var kept; the function (and the struct's inner vars staying inside it) gone.
    assert "enum EState { ES_Idle, ES_Run };" in stub
    assert "struct Pair { var int A; var int B; };" in stub
    assert "var EState State;" in stub
    assert "Helper" not in stub
    assert "local int x" not in stub


def test_it_does_not_let_a_brace_in_a_string_end_a_discarded_body_early():
    # Arrange — a `}` inside a string literal inside a discarded function body.
    src = textwrap.dedent("""
        class Talker extends Object;

        function Say() { Log("end brace } here"); }

        defaultproperties
        {
            Greeting="hi"
        }
    """)

    # Act
    stub = render_stub(parse_class(src))

    # Assert — defaultproperties survives (the string `}` did not end the body early).
    assert 'Greeting="hi"' in stub
    assert "Say" not in stub
    assert "end brace" not in stub


def test_it_rewrites_mesh_and_texture_import_files_to_munged_paths():
    # Arrange — decompiled source-filename ANIVFILE/DATAFILE and a stale TEXTURE FILE.
    src = textwrap.dedent(r"""
        class Ammo extends Pickup;

        #exec MESH IMPORT MESH=GEPAmmo ANIVFILE=Models\old_a.3d DATAFILE=Models\old_d.3d
        #exec TEXTURE IMPORT NAME=GEPAmmoTex1 FILE=Textures\stale.pcx GROUP=Skins

        defaultproperties
        {
        }
    """)

    # Act
    stub = render_stub(rewrite_imports(parse_class(src)))

    # Assert — mesh files keyed off MESH=, texture FILE off NAME=; stale paths gone.
    assert r"ANIVFILE=Models\GEPAmmo_a.3d" in stub
    assert r"DATAFILE=Models\GEPAmmo_d.3d" in stub
    assert r"FILE=Textures\GEPAmmoTex1.pcx" in stub
    assert "old_a.3d" not in stub
    assert "stale.pcx" not in stub


def test_parse_meshmap_scales_reads_directives_without_a_class_decl():
    # Arrange — umodel's per-mesh `.uc` may carry NO `class ...;` (G-uc); the scale reader copes.
    text = "#exec MESHMAP SCALE MESHMAP=WineBottle X=0.0316704 Y=0.0316704 Z=0.05\nrandom junk\n"

    # Act
    scales = parse_meshmap_scales(text)

    # Assert
    assert set(scales) == {"winebottle"}
    assert scales["winebottle"].props["X"] == "0.0316704"


def test_it_replaces_meshmap_scale_with_the_umodel_value_when_present():
    # Arrange — class's decompiled scale is a placeholder; umodel has the authoritative one.
    src = textwrap.dedent("""
        class Bottle extends Decoration;

        #exec MESHMAP SCALE MESHMAP=WineBottle X=1.0 Y=1.0 Z=1.0

        defaultproperties
        {
        }
    """)
    scales = parse_meshmap_scales("#exec MESHMAP SCALE MESHMAP=WineBottle X=0.0316704 Y=0.0316704 Z=0.05")

    # Act
    stub = render_stub(reconcile_meshmap_scale(parse_class(src), scales))

    # Assert — replaced in place.
    assert "X=0.0316704" in stub
    assert "X=1.0" not in stub


def test_it_keeps_the_decompiled_meshmap_scale_on_a_miss():
    # Arrange — umodel has a DIFFERENT mesh's scale; the class's own scale must survive.
    src = textwrap.dedent("""
        class Bottle extends Decoration;

        #exec MESHMAP SCALE MESHMAP=WineBottle X=1.0 Y=1.0 Z=1.0

        defaultproperties
        {
        }
    """)
    scales = parse_meshmap_scales("#exec MESHMAP SCALE MESHMAP=GEPAmmo X=0.03 Y=0.03 Z=0.03")

    # Act
    stub = render_stub(reconcile_meshmap_scale(parse_class(src), scales))

    # Assert — kept (keep-on-miss).
    assert "MESHMAP=WineBottle X=1.0 Y=1.0 Z=1.0" in stub


def test_it_rehomes_only_the_packages_own_self_refs_in_defaults():
    # Arrange — a self ref (Widget.*) and a foreign ref (OtherPkg.*).
    src = textwrap.dedent("""
        class Widget extends Actor;

        defaultproperties
        {
            Mesh=Mesh'Widget.WidgetMesh'
            Skin=Texture'OtherPkg.WidgetSkin'
        }
    """)

    # Act
    stub = render_stub(rehome_self_refs(parse_class(src), package="Widget", temp="StubTmp"))

    # Assert — only the package's OWN ref is re-homed; the foreign one is verbatim.
    assert "Mesh'StubTmp.WidgetMesh'" in stub
    assert "Texture'OtherPkg.WidgetSkin'" in stub
    assert "Widget.WidgetMesh" not in stub


def test_it_flags_foreign_package_asset_refs_in_defaults():
    # Arrange — one foreign ref, one self ref.
    src = textwrap.dedent("""
        class Widget extends Actor;

        defaultproperties
        {
            AmbientSound=Sound'AmbientSounds.Wind'
            Mesh=Mesh'Widget.WidgetMesh'
        }
    """)

    # Act
    flags = flag_cross_package_refs(parse_class(src), package="Widget")

    # Assert — only the foreign ref is flagged.
    assert len(flags) == 1
    assert flags[0].package == "AmbientSounds"
    assert flags[0].ref == "Sound'AmbientSounds.Wind'"


def test_read_uc_falls_back_to_iso_8859_1_on_non_utf8_bytes(tmp_path):
    # Arrange — 0xe9 ("é" in latin-1) is invalid utf-8.
    p = tmp_path / "X.uc"
    p.write_bytes(b"class X extends Object;\n// caf\xe9 comment\n")

    # Act
    text = read_uc(p)

    # Assert
    assert "class X extends Object;" in text
    assert "caf\xe9 comment" in text


def test_it_renames_group_prefixed_pcx_to_bare_and_leaves_bare_files(tmp_path):
    # Arrange
    (tmp_path / "Skins.GEPAmmoTex1.pcx").write_bytes(b"x")
    (tmp_path / "AlreadyBare.pcx").write_bytes(b"y")

    # Act
    renamed = rename_group_prefixed_pcx(tmp_path)

    # Assert
    assert (tmp_path / "GEPAmmoTex1.pcx").exists()
    assert not (tmp_path / "Skins.GEPAmmoTex1.pcx").exists()
    assert (tmp_path / "AlreadyBare.pcx").exists()
    assert renamed == {"Skins.GEPAmmoTex1.pcx": "GEPAmmoTex1.pcx"}


def test_it_fails_loud_on_a_pcx_base_name_collision(tmp_path):
    # Arrange — two group-prefixed files collapsing to the same bare name.
    (tmp_path / "Skins.Tex.pcx").write_bytes(b"x")
    (tmp_path / "Other.Tex.pcx").write_bytes(b"y")

    # Act / Assert
    with pytest.raises(UScriptParseError):
        rename_group_prefixed_pcx(tmp_path)


def test_it_finds_the_real_class_decl_past_a_banner_comment_mentioning_class():
    # Arrange — a UCC-style banner comment that contains the word "class" before the real decl.
    src = textwrap.dedent("""\
        //=============================================================================
        // GEPAmmo. Do not use this class directly.
        //=============================================================================
        class GEPAmmo extends Ammo;

        defaultproperties
        {
        }
    """)

    # Act
    cls = parse_class(src)

    # Assert — the real decl, not "directly" from the comment.
    assert cls.name == "GEPAmmo"
    assert cls.parent == "Ammo"


def test_it_preserves_a_package_qualified_parent_class():
    # Arrange
    src = "class Baz extends Engine.Actor;\ndefaultproperties\n{\n}\n"

    # Act
    cls = parse_class(src)

    # Assert — the qualifier is not truncated to "Engine".
    assert cls.parent == "Engine.Actor"
    assert "extends Engine.Actor;" in render_stub(cls)


def test_it_raises_a_typed_error_on_a_malformed_enum_with_no_brace():
    # Arrange — `enum` with no `{` before EOF (truncated/garbage input).
    src = "class X extends Object;\nenum EBroken\n"

    # Act / Assert — typed error, not a bare ValueError traceback.
    with pytest.raises(UScriptParseError):
        parse_class(src)


def test_it_flags_a_cross_package_texture_in_a_meshmap_settexture_exec():
    # Arrange — a mesh skin bound to ANOTHER package's texture (the spec's deferred case).
    src = textwrap.dedent("""
        class Widget extends Actor;

        #exec MESHMAP SETTEXTURE MESHMAP=WidgetMesh NUM=0 TEXTURE=Foreign.Skin
        #exec MESHMAP SETTEXTURE MESHMAP=WidgetMesh NUM=1 TEXTURE=Widget.OwnSkin

        defaultproperties
        {
        }
    """)

    # Act
    flags = flag_cross_package_refs(parse_class(src), package="Widget")

    # Assert — the foreign texture is flagged; the package's own one is not.
    assert any(f.package == "Foreign" and f.ref == "Foreign.Skin" for f in flags)
    assert not any(f.package == "Widget" for f in flags)


def test_parse_meshmap_scales_tolerates_other_malformed_exec_lines():
    # Arrange — a valid scale line plus an unrelated #exec the strict parser would reject.
    text = textwrap.dedent("""\
        #exec MESHMAP SCALE MESHMAP=WineBottle X=0.03 Y=0.03 Z=0.05
        #exec LODPARAMS MINVERTS=4 some_bare_token
    """)

    # Act
    scales = parse_meshmap_scales(text)

    # Assert — the scale is still extracted; the odd line doesn't abort the whole read.
    assert set(scales) == {"winebottle"}


def test_it_raises_on_an_unterminated_construct_rather_than_dropping_keep_set():
    # Arrange — an unterminated `(` runs to EOF; the trailing `var` must not vanish silently.
    src = "class X extends Object;\nfunction Bad( {\nvar int Keep;\n"

    # Act / Assert
    with pytest.raises(UScriptParseError):
        parse_class(src)


def test_it_flags_a_three_part_cross_package_texture_ref_in_an_exec():
    # Arrange — real DeusExItems carries `TEXTURE=Effects.Electricity.Nano_SFX_A` (Pkg.Group.Name).
    src = textwrap.dedent("""
        class Widget extends Actor;

        #exec MESHMAP SETTEXTURE MESHMAP=WidgetMesh NUM=1 TEXTURE=Effects.Electricity.Nano_SFX_A

        defaultproperties
        {
        }
    """)

    # Act
    flags = flag_cross_package_refs(parse_class(src), package="Widget")

    # Assert — the foreign package is the FIRST dotted segment.
    assert any(f.package == "Effects" and f.ref == "Effects.Electricity.Nano_SFX_A" for f in flags)
