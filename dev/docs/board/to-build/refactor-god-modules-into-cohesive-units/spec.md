# Spec — split the god modules

Pure structure. No behavior change: no test is edited, every golden stays byte-identical, and no
call site outside the split modules changes. "Green" here means *no worse than the recorded
baseline* — the suite already has known failures unrelated to this item; see "Verification".

## Scope — three of the four named modules

| Module | Lines | Here? |
|-----------------|-------|---
| `uprops.py` | 1238 | yes — whole file |
| `propedit.py` | 1222 | yes — whole file |
| `utexture.py` | 1227 | the DECODER half only |
| `preview.py` | 2290 | no — owned elsewhere |

**`preview.py` is excluded, and its split is NOT covered by the item it defers to.**
`consolidate-level-preview-native-onto-the-actor` (`to-plan/`) is actively rewriting the file — step 1
extracts one `Projection` seam, and later steps ADD a perspective camera, a near clipper and a second
fill inner-loop. It does not decompose the file, and it makes it bigger. Splitting the same file here
would collide with that work, so the split waits, tracked by its own item
`split-preview-py-after-the-preview` rather than assumed to ride along.

**`utexture.py`'s package layer is excluded** — `_ci`, `Package`, `load_package`, `_read_props`.
`migrate-utexture-py-dxpkg-py-onto-the-unified` (`to-spec/`) moves those onto `upackage.py`; its own
spec lists the BC decoders, `detect_layout`/`Layout` and `mip0_to_rgb` under "Texture-specific
(KEEP)", so the two do not overlap.

## Target layout

Each split module becomes a package whose `__init__.py` re-exports the current public surface, so
every `uprops.X` / `propedit.X` call site keeps working untouched. `utexture.py` stays a flat module
and gains a flat sibling, because the migration item reshapes it shortly.

**Placement is exhaustive.** Every top-level symbol in each file is assigned below — 45 in
`propedit.py`, 57 in `uprops.py`. A symbol left unplaced is where an executor invents a policy
mid-slice, so there are no "and the rest" clauses.

**Every `__init__.py` also re-exports its siblings' names**, on top of whatever the table assigns
it. The tables say where a symbol LIVES, not what the package root exposes; the root exposes
every symbol the flat module DEFINED — **`_`-prefixed included** — because the tests read
`uprops._decode_property` (`test_uprops_category.py:52,62,71,91`), `uprops._super_fqcn`
(`test_uprops.py:136`), `uprops._class_script_source` (`test_uprops_defaults.py:114`) and
`propedit._fmt_dec` (`test_propedit.py:135-137`). "Public" is not the cut; "defined here" is. What the root does NOT
re-export is the module's own incidental imports (`re`, `struct`, `Decimal`, `typedprops`, `Prop`…):
those are bound on the flat module today, but nothing reads them through it, and re-exporting them
would mean binding stdlib names on a package root. The subset gate in `plan.md` excludes them for
exactly this reason. `propedit.TYPED_FIELDS` is read at eight call sites in
`cli/commands/`, `from uedcli.propedit import TYPED_FIELDS, parse_token` at `test_transform.py:287`,
`from uedcli.uprops import Prop` in seven test files — all of which resolve through the root.

**`uprops`'s 16 `upackage` re-exports are a separate contract** (`uprops.py:27-36`, marked
`# noqa: F401 (re-exported public API)`): `Package`, `PropertyTag`, `SchemaError`, `load_package`,
`read_property_tags`, `read_compact_index as _read_compact_index`, `read_fstring as _read_fstring`,
and the nine `PT_*` constants. Only three are actually reached through `uprops` anywhere in the tree
— `Package`, `SchemaError`, `load_package` (`classdefaults.py`, `classindex.py`, `schema_cache.py`,
and the tests). The other thirteen have no external reader; they stay re-exported because the
contract is "everything reachable today", not because something reads them.

**Each submodule imports those names from `..upackage` directly — never from the package root.**
All four layers need them (`values.py` alone uses `SchemaError` 24 times and `Package` 23), and
`from . import Package` inside a submodule is a circular import into a partially-initialised root.
Reproduce the two aliases (`read_compact_index as _read_compact_index`,
`read_fstring as _read_fstring`) in each file that uses them.

### `uedcli/uprops/` — layered `base` < `script` < `schema` < `values`

| Module | Holds |
|-------------|---
| `base.py` | `Prop`, `PROPERTY_TYPES`, `_KINDS_WITH_TYPE_REF`, `CPF_NET`, `_schema_guard`, `_safe_name`, `_last_compact`, `_STRUCT_BIN_SIZES`, `ValueStyle`, `CLI_STYLE`, `T3D_STYLE`, `format_float`, `format_float_t3d` |
| `script.py` | `_walk_expr`, `_skip_script`, `enum_values`, `_field_next`, `struct_children_ref`, `find_struct_export`, `struct_members`, `_decode_property`, `_EX_END_FUNCTION_PARMS` |
| `schema.py` | `class_export_index`, `own_class_properties`, `class_index_map`, `super_fqcn_by_index`, `_super_fqcn`, `super_fqcn`, `iter_classes`, `class_is_abstract`, `abstract_from_source`, `_class_script_source`, `resolve_class_properties`, `class_default_tags`, `_ABSTRACT_DECL`, `_ABSTRACT_KW`, `_BLOCK_COMMENT`, `_LINE_COMMENT` |
| `values.py` | `struct_tag_member_tree`, `zero_struct_tree`, `strip_member_tree`, `render_member_tree`, `member_keys`, `decode_array_tag`, `render_default_tag`, `render_object_ref`, `resolve_class_default_tags`, `resolve_class_defaults`, `resolve_type_export`, `resolve_enum_names`, `_decode_struct_bin`, `_decode_struct_bin_at`, `_struct_tree_at`, `_byte_member_text`, `_zero_member_text`, `_pkg_for_owner`, `struct_member_schema` |

Two placements are counter-intuitive and load-bearing:

- **`_decode_property` goes in `script.py`, not `schema.py`.** It calls `enum_values`
  (`uprops.py:142`) and `struct_members` calls IT (`uprops.py:709`) — both in `script`. Moving it to
  `schema` would make `script → schema`, the upward edge. (`schema → script` is downward and legal;
  two such edges already exist and are fine.)
- **`class_default_tags` goes in `schema.py`, not `script.py`**, because it calls
  `class_export_index`. Leaving it in `script` is the one back-edge that makes the layering a cycle.

### `uedcli/propedit/` — layered `base` < `tokens` < `paths` < `structtext` < `fields` < top

| Module | Holds |
|----------------|---
| `base.py` | `PropEditError`, `HARD_REJECT`, `STRUCT_FILL`, `_dequote`, `_dec_finite`, `_fmt_dec`, `_NUM_BOUND`, `_IDENT_RE`, `_INT_RE`, `_PAREN_KEY_RE`, `_PAREN_ANY_RE`, `_VR_STRUCTS` |
| `tokens.py` | `PropToken`, `ClassCtx`, `parse_token`, `check_hard_reject`, `check_overlaps` |
| `paths.py` | `MemberStep`, `ResolvedPath`, `resolve_path`, `_member_map`, `_text_key_ident` |
| `structtext.py`| `split_struct_text`, `emit_struct_text`, `merge_struct_texts`, `full_struct_text`, `zero_value`, `_set_member_in_text`, `_unset_member_in_text`, `_maybe_comma_sugar`, `validate_leaf_value`, `_canonicalize_enum`, `_canon_scalar`, `_validate_query_value` |
| `fields.py` | `TypedField`, `ScaleField`, `TYPED_FIELDS` |
| `__init__.py` | `Plan`, `plan_edit`, `get_lines`, `dump_all_lines`, `effective_value`, `effective_match`, `values_match`, `_stored_map` |

**`zero_value` goes in `structtext.py`, not `__init__.py`** — `full_struct_text` calls it
(`propedit.py:449`), and `full_struct_text` cannot import upward from the package root.

### `uedcli/utexture_codec.py`

`_rgb565`, `_bc_colours`, `_bc2_alpha`, `_bc3_alpha`, `_decode_block`, `_decode_bc1`, `_decode_bc2`,
`_decode_bc3`, `_decode_linear1`, `mip0_to_rgb`, `Layout`, `DetectionFailure`, `_fitting_classes`,
`detect_layout`, **and the five constants that code reads at runtime** — `_LINEAR_BPP`,
`_BLOCK_BYTES`, `_CODE_TO_CLASS`, `_CODE_TO_LAYOUT`, `_CLASS_TO_LAYOUT`. Omitting the constants is
what turns this slice into a circular import.

The moved code's only reference back into `utexture.py` is the `Mip` type, which appears solely in
annotations; `from __future__ import annotations` is already in force, so import it under
`if TYPE_CHECKING:` and no runtime edge exists.

`utexture.py` imports back the six names it still CALLS — `DetectionFailure`, `detect_layout`,
`_decode_bc1`/`_bc2`/`_bc3`, `_decode_linear1` (via `_DECODERS` at `utexture.py:531` and
`TextureResolver`). That is not the whole re-export list: the tests read moved symbols as
`utexture.X`, including `_`-prefixed ones — `_CODE_TO_CLASS`, `_CODE_TO_LAYOUT`, `_fitting_classes`,
`Layout`, `_bc2_alpha`, `_bc3_alpha`, `mip0_to_rgb`. `_bc2_alpha`/`_bc3_alpha` are read inside a
`@pytest.mark.parametrize` at `test_utexture_blocks.py:369-370`, so missing them is a COLLECTION
error, not a test failure. The module has no `__all__`; enumerate the re-export list from the current
file before moving anything, `_`-prefixed included.

## How the layerings were derived

Each grouping was checked by building the intra-module reference graph with `ast` and asserting no
edge points up the layer order, with the placement covering every top-level symbol. Both are DAGs
under the orders given. Re-run that check after any placement change rather than reasoning about it —
the first draft of this spec asserted a layering that was provably cyclic.

## Constraints

- **No public rename.** Anything reachable as `module.name` today stays reachable as `module.name`.
- **No signature changes** and **no lazy in-function imports to break a cycle.** If a cycle appears,
  the placement is wrong; fix the placement.
- **`_`-prefixed does not mean private to the file.** Grep every symbol's callers, tests included,
  before moving it.
- **Leave the monkeypatch seams alone.** Three bare-global calls stop being interceptable from the
  package root once their callee moves into a sibling: `resolve_class_properties → own_class_properties`
  (`uprops.py:381`, `:397`), `resolve_class_properties → load_package` (`:396`, bound from
  `..upackage` after the split), and `resolve_class_defaults → resolve_class_properties` (`:1212`,
  a cross-module import after the split). No test in the suite depends on any of the three.
  Every consumer patches and reads the module ATTRIBUTE (`schema_cache.py:278` is
  `uprops.own_class_properties(...)`), which keeps resolving through the package root. Re-pointing
  `test_schema_cache.py:114` at `uedcli.uprops.schema` would install its spy where `schema_cache`
  never looks and make `assert calls[0] == 0` pass vacuously. `test_ingest_validation.py:416` is
  likewise unaffected — `resolve_class_properties` is already replaced by `_boom` at `:411`, so the
  intra-module call site never runs. `_spy_load_package` (`test_schema_cache.py`) reaches
  `load_package` as an attribute too, and all three `resolve_class_properties` patchers
  (`test_ingest_validation.py:272`, `:411`, `:437`) also stub `resources.class_defaults`, so the
  `:1212` path is not what they measure. Checked across every `monkeypatch.setattr` against
  `uprops`/`propedit`/`utexture`, and confirmed by running the suite against an executed split: the
  failure set is unchanged. Do not "fix" this.
- **Relative-import depth changes.** Inside `uedcli/uprops/*.py` and `uedcli/propedit/*.py`, `.` now
  means the new package, not `uedcli` — every `from .x import` and `from . import x` in the moved
  code becomes `..`. Five of them are FUNCTION-LOCAL, so they resolve at call time and a
  module-import smoke test never reaches them. The complete list:

  | Site | Import |
  |----------------------------------------|---
  | `uprops.py:359` `resolve_class_properties` | `from . import schema_cache` (a documented lazy cycle-break) |
  | `propedit.py:696` `plan_edit` | `from . import movers` |
  | `propedit.py:892` `ScaleField._fs` | `from .transform import IDENTITY` |
  | `propedit.py:939` `ScaleField._parse_whole` | `from .transform import DEFAULT_SHEER_AXIS, FScale` |
  | `propedit.py:975` `ScaleField.apply` | `from .transform import IDENTITY, FScale` |

  Miss one and the module still imports: `actor prop set NumKeys=4` or any `MainScale` edit raises
  `ModuleNotFoundError` at the call. The full suite covers both paths, so run it — do not trust a
  clean import.
- **`pyproject.toml`'s `packages` list is static, not `find_packages`.** Two new subpackages must be
  added or the wheel ships without them.

## Verification

- `bin/test` with no test edited, and no failure that was not already failing before the slice.
  **The suite is NOT green on master**, so re-measure the baseline before starting and compare
  against it. Measured at `2e8f600` with the native extension built — five failures:

  | Test | Cause |
  |------------------------------------------------------------|---
  | `test_import_verb.py::test_imported_class_names_reach_the_trunk_fully_qualified` | `_AnyTexture` stub vs `f89334b`'s `class_index=` kwarg — item `master-red-anytexture-test-double-not-updated` |
  | `test_import_verb.py::test_the_scratch_drop_happens_before_qualification_in_the_real_pipeline` | same |
  | `test_doc_links.py::test_no_citation_of_a_deleted_doc` | `decisions.md` substring — item `master-red-unified-asset-catalog-spec-questions` |
  | `test_board_script.py::test_ls_json_on_an_empty_stage_is_an_empty_array` | `stale/` is non-empty |
  | `test_driver.py::test_screenshot_shoots_into_work_then_cps_out_to_the_host_path` | host-dependent (writes a literal `/host/out/` path) |

  **The two `test_import_verb` failures raise from `utexture.TextureResolver`** — the very seam
  slice 1 cuts. They are pre-existing; do not read them as slice 1 breaking something. Without the
  native extension built the count is far higher (26 more in `test_preview_faces.py`), so record the
  baseline on the same setup you will gate against.
- A new import-layering test (see `plan.md`) — the existing `test_command_isolation.py` does **not**
  cover this: its `_HEAVY` sentinels name `apply`/`materialize`/`editor`/`preview_*`/`native`/`PIL`,
  none of these modules, and its other cases only assert that one family does not load another. `test_import_boundary.py`'s cycle rule fires only on cycles containing a `cli` module.
- `actor prop get`/`set`/`unset` exercised by hand on a real trunk after slice 3 — `propedit` is a
  write path, and a golden-free regression there is a silent data bug.
