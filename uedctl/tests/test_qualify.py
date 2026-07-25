import pytest

from uedctl.model import Actor, Brush, Level, Polygon
from uedctl.qualify import parse_loaded_classes, parse_obj_dependencies, qualify_level_textures

_CLASS_LIST_DUMP = """\
Log: Class Core.Object                                                                    1328       1328
Log: Class UnrealShare.UnrealTestInfo                                                     1920       1920
Log: Class UnrealShareDupe.UnrealTestInfo                                                 1920       1920
Log: Class Engine.Brush                                                                   1316       1316
"""


def test_parse_loaded_classes_groups_by_bare_name():
    assert parse_loaded_classes(_CLASS_LIST_DUMP) == {
        "Object": {"Core.Object"},
        "UnrealTestInfo": {"UnrealShare.UnrealTestInfo", "UnrealShareDupe.UnrealTestInfo"},
        "Brush": {"Engine.Brush"},
    }


def test_parse_loaded_classes_ignores_non_class_lines():
    dump = ("Log: Class Engine.Brush                100  100\n"
            "Log:  \n"
            "Log: Class                           Count  NumKBytes  MaxKBytes\n")
    assert parse_loaded_classes(dump) == {"Brush": {"Engine.Brush"}}


def test_parse_loaded_classes_matches_a_line_with_no_trailing_columns():
    # A trimmed/truncated final line (no count columns after the class name) must still match --
    # only the "Class   Count  NumKBytes  MaxKBytes" HEADER line (no '.' in its second token)
    # needs excluding, not every line lacking trailing whitespace.
    assert parse_loaded_classes("Log: Class Engine.Brush") == {"Brush": {"Engine.Brush"}}


_SIX_FACE_CUBE_DUMP = """\
Package MyLevel references:
   Class Engine.Polys
   Texture CoreTexMetal.Metal.Area51Wall_A
   Texture Area51Textures.Metal.Area51Wall_A
   Texture Engine.DefaultTexture
   Texture Engine.DefaultTexture
   Texture Engine.DefaultTexture
   Texture Engine.DefaultTexture
"""

_TWO_BRUSH_DUMP = """\
Package MyLevel references:
   Class Engine.Polys
   Texture CoreTexMetal.Metal.Area51Wall_A
   Class Engine.Polys
   Texture Area51Textures.Metal.Area51Wall_A
"""


def test_parse_single_block_in_poly_order():
    blocks = parse_obj_dependencies(_SIX_FACE_CUBE_DUMP)
    assert blocks == [[
        "CoreTexMetal.Metal.Area51Wall_A",
        "Area51Textures.Metal.Area51Wall_A",
        "Engine.DefaultTexture",
        "Engine.DefaultTexture",
        "Engine.DefaultTexture",
        "Engine.DefaultTexture",
    ]]


def test_parse_separates_one_block_per_brush():
    blocks = parse_obj_dependencies(_TWO_BRUSH_DUMP)
    assert blocks == [["CoreTexMetal.Metal.Area51Wall_A"],
                      ["Area51Textures.Metal.Area51Wall_A"]]


def test_parse_ignores_lines_outside_a_polys_block():
    dump = ("Package MyLevel references:\n"
            "   Class Engine.Model\n"
            "   Texture Engine.DefaultTexture\n"      # NOT inside an Engine.Polys block
            "   Class Engine.Polys\n"
            "   Texture CoreTexMetal.Metal.Area51Wall_A\n")
    assert parse_obj_dependencies(dump) == [["CoreTexMetal.Metal.Area51Wall_A"]]


def test_parse_returns_empty_list_for_no_polys_blocks():
    assert parse_obj_dependencies("Package MyLevel references:\n   Class Core.Object\n") == []


# --- correlating dump blocks with a Level (Task 4, D-Q2) --------------------

def _brush_actor(name: str, polys: list[Polygon]) -> Actor:
    a = Actor(name=name, cls="Brush")
    a.brush = Brush(model_name=f"{name}Model")
    a.brush.polys = polys
    return a


def test_qualify_patches_only_already_textured_polys_in_order():
    lvl = Level()
    p_textured_1 = Polygon(texture="Area51Wall_A")
    p_unset = Polygon(texture=None)
    p_textured_2 = Polygon(texture="DefaultTexture")
    lvl.actors["B1"] = _brush_actor("B1", [p_textured_1, p_unset, p_textured_2])
    lvl.order = ["B1"]

    qualify_level_textures(lvl, [["CoreTexMetal.Metal.Area51Wall_A", "Engine.DefaultTexture"]])

    assert p_textured_1.texture == "CoreTexMetal.Area51Wall_A"    # group stripped (D-Q2 follow-up)
    assert p_unset.texture is None                     # never touched
    assert p_textured_2.texture == "Engine.DefaultTexture"        # already 2-part, unchanged


def test_qualify_binds_same_name_different_package_brushes_by_block_order():
    # Two brushes share the SAME object-name (`Area51Wall_A`) but resolve to DIFFERENT packages.
    # Content (object-name) matching CANNOT disambiguate them -- both blocks match both brushes --
    # so the tie is broken by BLOCK ORDER, which by the engine invariant (dump block order ==
    # authored/MAP EXPORT brush order, spikes/2026-06-19-read-surface-texture-package.md) equals
    # `level.order`. Blocks in authored order => each brush gets its correct package.
    lvl = Level()
    pA = Polygon(texture="Area51Wall_A")
    pB = Polygon(texture="Area51Wall_A")
    lvl.actors["BrushB"] = _brush_actor("BrushB", [pB])
    lvl.actors["BrushA"] = _brush_actor("BrushA", [pA])
    lvl.order = ["BrushA", "BrushB"]          # order is authoritative, not dict insertion

    qualify_level_textures(lvl, [["CoreTexMetal.Metal.Area51Wall_A"],
                                 ["Area51Textures.Metal.Area51Wall_A"]])

    assert pA.texture == "CoreTexMetal.Area51Wall_A"
    assert pB.texture == "Area51Textures.Area51Wall_A"


def test_qualify_same_name_diff_package_relies_on_block_order_a_reorder_would_swap():
    # DOCUMENTS the one load-bearing dependence on order (see qualify docstring "LOAD-BEARING
    # LIMIT"): if the two same-object-name blocks arrive REVERSED vs level.order, the packages
    # swap -- SILENTLY (object-names still match, so no raise). This test pins that reality so a
    # future change to block/empty/aggregate ordering that breaks the 2026-06-19 invariant fails
    # HERE (loudly, in CI) instead of silently mis-binding a real level's textures.
    lvl = Level()
    pA = Polygon(texture="Area51Wall_A")
    pB = Polygon(texture="Area51Wall_A")
    lvl.actors["BrushA"] = _brush_actor("BrushA", [pA])
    lvl.actors["BrushB"] = _brush_actor("BrushB", [pB])
    lvl.order = ["BrushA", "BrushB"]
    # blocks REVERSED relative to order -> first-unclaimed gives BrushA the SECOND package
    qualify_level_textures(lvl, [["Area51Textures.Metal.Area51Wall_A"],
                                 ["CoreTexMetal.Metal.Area51Wall_A"]])
    assert pA.texture == "Area51Textures.Area51Wall_A"    # NOT content-disambiguated: order decides
    assert pB.texture == "CoreTexMetal.Area51Wall_A"


def test_qualify_strips_a_deeper_multi_segment_group_too():
    lvl = Level()
    poly = Polygon(texture="SomeTexture")     # authored object-name matches the dump block's
    lvl.actors["B1"] = _brush_actor("B1", [poly])
    lvl.order = ["B1"]

    qualify_level_textures(lvl, [["SomePkg.GroupA.GroupB.SomeTexture"]])

    assert poly.texture == "SomePkg.SomeTexture"      # only first + last segment kept


def test_qualify_drops_the_world_model_aggregate_block_wherever_it_sits():
    # The level's own world BSP Model contributes ONE extra NON-EMPTY Engine.Polys block: the
    # AGGREGATE of every brush's surfaces. Its POSITION among the non-empty blocks is not stable
    # (live 2026-07-14: last for 2 brushes, FIRST for the 95-brush castle, middle for a
    # World-shell level -- probe_tree.py / probe_aggregate.py). Content matching leaves it
    # unclaimed and drops it no matter where it sits -- here it is FIRST, ahead of the brush's
    # own block, which a "drop the trailing block" scheme would have mis-bound.
    lvl = Level()
    poly = Polygon(texture="Wall_A")
    lvl.actors["B1"] = _brush_actor("B1", [poly])
    lvl.order = ["B1"]
    aggregate = ["World.Floor_A", "World.Wall_A", "World.Ceil_A"]      # 3-poly aggregate, FIRST
    qualify_level_textures(lvl, [aggregate, ["CoreTexMetal.Wall_A"]])
    assert poly.texture == "CoreTexMetal.Wall_A"       # bound to its OWN block, aggregate dropped


def test_qualify_does_not_mis_bind_when_aggregate_precedes_a_lone_brush():
    # Reviewer case: a SINGLE textured brush whose aggregate has the SAME poly count sits BEFORE
    # the brush's own block. A count-only scheme would bind the brush to the aggregate silently
    # (count 1 == 1) and drop the real block. Content matching binds by object-name, so the
    # aggregate (different object-name) is never claimed by the brush.
    lvl = Level()
    poly = Polygon(texture="Wall_A")
    lvl.actors["B1"] = _brush_actor("B1", [poly])
    lvl.order = ["B1"]
    qualify_level_textures(lvl, [["World.SomethingElse"], ["CoreTexMetal.Wall_A"]])
    assert poly.texture == "CoreTexMetal.Wall_A"       # NOT "World.SomethingElse"


def test_qualify_binds_a_multi_texture_brush_in_poly_order():
    lvl = Level()
    p0 = Polygon(texture="Floor_A")
    p1 = Polygon(texture="Wall_B")
    lvl.actors["B1"] = _brush_actor("B1", [p0, p1])
    lvl.order = ["B1"]
    # aggregate FIRST (same two names, but that's the world Model, a separate block); brush second
    qualify_level_textures(lvl, [["W.Floor_A", "W.Wall_B"],
                                 ["CoreTex.Floor.Floor_A", "CoreTex.Wall.Wall_B"]])
    # Bound to the SECOND block (its own) -- the two blocks share object-names, and first-unclaimed
    # picks block 0 for the brush, which is fine: block 0's object-names match in order too.
    assert p0.texture == "W.Floor_A"
    assert p1.texture == "W.Wall_B"


def test_qualify_raises_when_a_brush_has_no_matching_block():
    # A brush with textured polys but no block whose object-names match (fewer blocks, or a
    # missing/misnamed texture, or dump poly-order drift) -> loud raise, never a silent mis-bind.
    lvl = Level()
    lvl.actors["B1"] = _brush_actor("B1", [Polygon(texture="Present_A")])
    lvl.actors["B2"] = _brush_actor("B2", [Polygon(texture="Absent_B")])
    lvl.order = ["B1", "B2"]
    with pytest.raises(ValueError, match="no OBJ DEPENDENCIES.*block matches brush 'B2'.*Absent_B"):
        qualify_level_textures(lvl, [["CoreTex.Present_A"]])


def test_qualify_drops_empty_blocks_on_both_sides():
    # The level's own internal BSP Model contributes an EMPTY Engine.Polys block too (confirmed
    # live 2026-06-20) -- it is filtered out as non-empty before matching.
    lvl = Level()
    poly = Polygon(texture="Area51Wall_A")
    lvl.actors["B1"] = _brush_actor("B1", [poly])
    lvl.order = ["B1"]
    qualify_level_textures(lvl, [[], ["CoreTexMetal.Area51Wall_A"]])
    assert poly.texture == "CoreTexMetal.Area51Wall_A"


def test_qualify_skips_a_brush_with_no_textured_polys_at_all():
    # A brush with every poly unset produces NO block at all (not an empty one to drop -- it
    # simply isn't on either side of the correlation).
    lvl = Level()
    untextured = Polygon(texture=None)
    textured = Polygon(texture="Area51Wall_A")
    lvl.actors["Untextured"] = _brush_actor("Untextured", [untextured])
    lvl.actors["Textured"] = _brush_actor("Textured", [textured])
    lvl.order = ["Untextured", "Textured"]
    qualify_level_textures(lvl, [["CoreTexMetal.Area51Wall_A"]])
    assert untextured.texture is None
    assert textured.texture == "CoreTexMetal.Area51Wall_A"


def test_qualify_raises_on_poly_count_mismatch_within_a_brush():
    # A block whose object-name SEQUENCE differs in length from the brush's textured polys can
    # never match -> loud raise (a length-2 want vs a length-1 block).
    lvl = Level()
    lvl.actors["B1"] = _brush_actor("B1", [Polygon(texture="X"), Polygon(texture="Y")])
    lvl.order = ["B1"]
    with pytest.raises(ValueError, match="no OBJ DEPENDENCIES.*block matches brush 'B1'"):
        qualify_level_textures(lvl, [["only-one"]])


# --- qualify_level_classes ---------------------------------------------------

from uedctl.qualify import qualify_level_classes


def test_qualify_level_classes_qualifies_an_unambiguous_bare_class():
    lvl = Level()
    lvl.actors["L1"] = Actor(name="L1", cls="UnrealTestInfo")
    lvl.order = ["L1"]
    qualify_level_classes(lvl, {"UnrealTestInfo": {"UnrealShare.UnrealTestInfo"}})
    assert lvl.actors["L1"].cls == "UnrealShare.UnrealTestInfo"


def test_qualify_level_classes_leaves_an_already_qualified_class_untouched():
    lvl = Level()
    lvl.actors["L1"] = Actor(name="L1", cls="UnrealShare.UnrealTestInfo")
    lvl.order = ["L1"]
    qualify_level_classes(lvl, {"UnrealTestInfo": {"UnrealShare.UnrealTestInfo",
                                                    "UnrealShareDupe.UnrealTestInfo"}})
    assert lvl.actors["L1"].cls == "UnrealShare.UnrealTestInfo"      # not re-derived, not touched


def test_qualify_level_classes_raises_on_an_unresolvable_class():
    lvl = Level()
    lvl.actors["L1"] = Actor(name="L1", cls="GhostClass")
    lvl.order = ["L1"]
    with pytest.raises(ValueError, match="L1.*GhostClass.*not.*loaded"):
        qualify_level_classes(lvl, {"UnrealTestInfo": {"UnrealShare.UnrealTestInfo"}})


def test_qualify_level_classes_raises_on_a_genuine_collision():
    lvl = Level()
    lvl.actors["L1"] = Actor(name="L1", cls="UnrealTestInfo")
    lvl.order = ["L1"]
    with pytest.raises(ValueError,
                       match="L1.*UnrealTestInfo.*UnrealShare.UnrealTestInfo.*UnrealShareDupe.UnrealTestInfo|"
                             "L1.*UnrealTestInfo.*UnrealShareDupe.UnrealTestInfo.*UnrealShare.UnrealTestInfo"):
        qualify_level_classes(lvl, {"UnrealTestInfo": {"UnrealShare.UnrealTestInfo",
                                                        "UnrealShareDupe.UnrealTestInfo"}})


def test_qualify_level_classes_processes_every_actor_in_order():
    lvl = Level()
    lvl.actors["L1"] = Actor(name="L1", cls="Brush")
    lvl.actors["L2"] = Actor(name="L2", cls="UnrealTestInfo")
    lvl.order = ["L1", "L2"]
    qualify_level_classes(lvl, {"Brush": {"Engine.Brush"},
                               "UnrealTestInfo": {"UnrealShare.UnrealTestInfo"}})
    assert lvl.actors["L1"].cls == "Engine.Brush"
    assert lvl.actors["L2"].cls == "UnrealShare.UnrealTestInfo"


# --- driving the live read (Task 5) -----------------------------------------

def test_dump_obj_dependencies_returns_once_the_completion_marker_appears():
    from unittest import mock
    from uedctl.qualify import dump_obj_dependencies
    driver = mock.Mock()
    driver.log_size.return_value = 500
    driver.dismiss_blocking_dialog.return_value = False
    # first read mid-buffer (header present, terminator not yet -- the 4KB-buffering case);
    # second has the terminator.
    driver.read_log_since.side_effect = [
        "Log: Dependencies of MyLevel:\nLog:    Class Engine.Polys\n",
        "Log: Dependencies of MyLevel:\nLog:    Class Engine.Polys\n"
        "Log: Objects:\nLog: 0 Deleted Objects\n",
    ]
    with mock.patch("time.sleep", autospec=True) as sleep:
        text = dump_obj_dependencies(driver)
    assert "Class Engine.Polys" in text
    assert "Deleted Objects" not in text       # _blocks_only cuts at the Objects: terminator
    driver.obj_dependencies.assert_called_once_with("MyLevel")
    assert driver.exec.call_args_list == [mock.call("OBJ LIST CLASS=Class")] * 2
    assert driver.dismiss_blocking_dialog.call_count == 2     # tried before every attempt
    assert sleep.call_count == 2
    assert driver.read_log_since.call_args_list == [mock.call(500), mock.call(500)]


def test_dump_obj_dependencies_ignores_a_stale_earlier_walks_completion_marker():
    # A read can surface a PRIOR walk's "Dependencies of MyLevel:"/"Deleted Objects" pair that
    # happened to flush in the same burst (Editor.log's 4KB buffering) -- the bare marker alone
    # must not satisfy completion; only one occurring AFTER the LAST header counts.
    from unittest import mock
    from uedctl.qualify import dump_obj_dependencies
    driver = mock.Mock()
    driver.log_size.return_value = 0
    driver.dismiss_blocking_dialog.return_value = False
    driver.read_log_since.side_effect = [
        # stale walk's terminator, then a NEW header with no terminator of its own yet
        "Log: Dependencies of MyLevel:\nLog: Objects:\nLog: 0 Deleted Objects\n"
        "Log: Dependencies of MyLevel:\nLog:    Class Engine.Polys\n",
        # now the current walk's own terminator has flushed too
        "Log: Dependencies of MyLevel:\nLog: Objects:\nLog: 0 Deleted Objects\n"
        "Log: Dependencies of MyLevel:\nLog:    Class Engine.Polys\n"
        "Log: Objects:\nLog: 1 Deleted Objects\n",
    ]
    with mock.patch("time.sleep", autospec=True):
        text = dump_obj_dependencies(driver)
    assert driver.read_log_since.call_count == 2       # did NOT stop on the stale marker
    assert "Class Engine.Polys" in text


def test_dump_obj_dependencies_excludes_the_fillers_own_output_from_the_result():
    # OBJ LIST CLASS=Class lists a class literally named Engine.Polys -- confirmed live
    # 2026-06-20. Anything after the walk's own Objects: terminator must be excluded.
    from unittest import mock
    from uedctl.qualify import dump_obj_dependencies
    driver = mock.Mock()
    driver.log_size.return_value = 0
    driver.dismiss_blocking_dialog.return_value = False
    driver.read_log_since.return_value = (
        "Log: Dependencies of MyLevel:\nLog:    Class Engine.Polys\n"
        "Log:    Texture CoreTexMetal.Area51Wall_A\n"
        "Log: Objects:\nLog: 0 Deleted Objects\n"
        "Log: Class Engine.Polys                1328       1328\n"   # the filler's own listing
    )
    with mock.patch("time.sleep", autospec=True):
        text = dump_obj_dependencies(driver)
    assert text.count("Class Engine.Polys") == 1       # the filler's copy is excluded
    assert "1328" not in text


def test_dump_obj_dependencies_dismisses_a_stuck_dialog_each_attempt():
    from unittest import mock
    from uedctl.qualify import dump_obj_dependencies
    driver = mock.Mock()
    driver.log_size.return_value = 0
    driver.dismiss_blocking_dialog.return_value = True
    driver.read_log_since.return_value = "Log: Dependencies of MyLevel:\nLog: 1 Deleted Objects\n"
    with mock.patch("time.sleep", autospec=True):
        dump_obj_dependencies(driver)
    driver.dismiss_blocking_dialog.assert_called_once()       # one attempt was enough here


def test_dump_obj_dependencies_raises_timeout_rather_than_return_a_partial_dump():
    from unittest import mock
    import pytest
    from uedctl.qualify import dump_obj_dependencies
    driver = mock.Mock()
    driver.log_size.return_value = 0
    driver.dismiss_blocking_dialog.return_value = False
    driver.read_log_since.return_value = "Package MyLevel references:\n"   # no header at all
    with mock.patch("time.sleep", autospec=True), \
         pytest.raises(TimeoutError, match=r"did not complete within 3 attempts"):
        dump_obj_dependencies(driver, max_attempts=3, poll_interval=0.01)
    assert driver.read_log_since.call_count == 3


def test_qualify_live_level_dumps_parses_and_patches(monkeypatch):
    from unittest import mock
    import uedctl.qualify as qualify
    from uedctl.qualify import qualify_live_level
    lvl = Level()
    poly = Polygon(texture="Area51Wall_A")
    actor = Actor(name="B1", cls="Brush"); actor.brush = Brush(model_name="B1Model")
    actor.brush.polys = [poly]
    lvl.actors["B1"] = actor
    lvl.order = ["B1"]
    monkeypatch.setattr(qualify, "dump_obj_dependencies",
                        lambda driver: "Class Engine.Polys\nTexture Core.Metal.Area51Wall_A\n")
    driver = mock.Mock()
    driver.dismiss_blocking_dialog.return_value = False
    driver.read_log_since.return_value = "Log: Class Engine.Brush   1   1\n"
    with mock.patch("time.sleep", autospec=True):
        qualify_live_level(lvl, driver=driver)
    assert poly.texture == "Core.Area51Wall_A"        # group stripped end-to-end
    assert actor.cls == "Engine.Brush"                # bare actor class qualified too


def test_qualify_live_level_also_qualifies_classes(monkeypatch):
    from unittest import mock
    import uedctl.qualify as qualify
    from uedctl.qualify import qualify_live_level
    lvl = Level()
    lvl.actors["L1"] = Actor(name="L1", cls="UnrealTestInfo")
    lvl.order = ["L1"]
    monkeypatch.setattr(qualify, "dump_obj_dependencies", lambda driver: "")
    driver = mock.Mock()
    driver.dismiss_blocking_dialog.return_value = False
    driver.read_log_since.return_value = "Log: Class UnrealShare.UnrealTestInfo   1   1\n"
    with mock.patch("time.sleep", autospec=True):
        qualify_live_level(lvl, driver=driver)
    assert lvl.actors["L1"].cls == "UnrealShare.UnrealTestInfo"
    # `_read_loaded_classes` dismisses a stuck dialog before EVERY poll (not once), so a constant
    # read that stabilizes on the 2nd iteration yields two dismiss calls.
    assert driver.dismiss_blocking_dialog.call_count == 2


# --- _read_loaded_classes (settle-and-read, no natural completion marker) ---

from uedctl.qualify import _read_loaded_classes


def test_read_loaded_classes_waits_for_two_consecutive_identical_reads():
    from unittest import mock
    driver = mock.Mock()
    driver.log_size.return_value = 0
    driver.dismiss_blocking_dialog.return_value = False
    # Read 1 is mid-flush (partial); the SAME, now-complete text repeats on reads 2 and 3.
    # Stabilization requires the FIRST pair of consecutive identical reads (2 and 3), so the
    # function must keep polling past read 1 rather than trusting any single read alone.
    driver.read_log_since.side_effect = [
        "Log: Class Core.Object   1   1\n",
        "Log: Class Core.Object   1   1\nLog: Class Engine.Brush   1   1\n",
        "Log: Class Core.Object   1   1\nLog: Class Engine.Brush   1   1\n",
    ]
    with mock.patch("time.sleep", autospec=True) as sleep:
        result = _read_loaded_classes(driver)
    assert result == {"Object": {"Core.Object"}, "Brush": {"Engine.Brush"}}
    assert driver.read_log_since.call_count == 3
    assert sleep.call_count == 3
    # Flush-filler AND dialog-dismiss are re-driven EACH iteration (mirroring `dump_obj_dependencies`),
    # not once before the loop, so a mid-load GC "Cleaning up..." dialog can't permanently wedge the
    # poll and the 4KB log buffer keeps getting pushed past its boundary while classes still stream in.
    assert driver.exec.call_args_list == [mock.call("OBJ LIST CLASS=Class")] * 3
    assert driver.dismiss_blocking_dialog.call_count == 3


def test_read_loaded_classes_raises_timeout_rather_than_return_a_partial_map():
    from unittest import mock
    import pytest
    driver = mock.Mock()
    driver.log_size.return_value = 0
    driver.dismiss_blocking_dialog.return_value = False
    # Never stabilizes -- a new class appears on every single read.
    driver.read_log_since.side_effect = [
        "Log: Class Core.Object   1   1\n",
        "Log: Class Core.Object   1   1\nLog: Class Engine.Brush   1   1\n",
        "Log: Class Core.Object   1   1\nLog: Class Engine.Brush   1   1\n"
        "Log: Class Engine.Light   1   1\n",
    ]
    with mock.patch("time.sleep", autospec=True), \
         pytest.raises(TimeoutError, match=r"did not stabilize within 3 attempts"):
        _read_loaded_classes(driver, max_attempts=3, poll_interval=0.01)
    assert driver.read_log_since.call_count == 3
