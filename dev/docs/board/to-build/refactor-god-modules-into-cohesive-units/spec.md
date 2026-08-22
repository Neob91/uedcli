# Spec — split the god modules

Pure structure. No behavior change, no user-visible effect: every test passes unchanged, every
golden stays byte-identical, and no call site outside the split modules is edited.

## Scope — three of the four named modules

The item names four offenders. Two of them are already owned by other items, so this covers what is
left. Measured at `fc8e7fc`:

| Module | Lines | Here? |
|-----------------|-------|---
| `uprops.py` | 1238 | yes — whole file |
| `propedit.py` | 1222 | yes — whole file |
| `utexture.py` | 1227 | the DECODER half only |
| `preview.py` | 2290 | no — see below |

**`preview.py` is excluded.** `consolidate-level-preview-native-onto-the-actor` (`to-plan/`) has it:
its step 1 is "extract a `Projection` seam, NO behaviour change", gated on the `actor preview`
goldens staying byte-identical, and later steps add a perspective camera and retire
`preview_native.py`'s Rust rasterizer. Splitting the same file here would collide head-on. Its line
count is also 424 lower than this item records — `6d8f770` removed the legend and name machinery
after the survey was written.

**`utexture.py`'s package layer is excluded** — `Package`, `load_package`, `_ci`, `_read_props`.
`migrate-utexture-py-dxpkg-py-onto-the-unified` (`to-spec/`) moves those onto `upackage.py`. The
decoder and layout-detection halves are untouched by that item and are split here.

## Target layout

Each module becomes a package whose `__init__.py` re-exports the current public surface, so every
existing `uprops.X` / `propedit.X` / `utexture.X` call site keeps working untouched. That is what
makes this a zero-call-site refactor rather than a rename sweep.

**`uedcli/uprops/`** — three concerns that share only the `Package` handle:

| New module | Holds |
|--------------|---
| `schema.py` | class hierarchy + property schema: `class_export_index`, `own_class_properties`, `class_index_map`, `super_fqcn`/`_super_fqcn`/`super_fqcn_by_index`, `iter_classes`, `class_is_abstract`, `abstract_from_source`, `_class_script_source`, `resolve_class_properties` |
| `script.py` | the UnrealScript bytecode/field graph: `_walk_expr`, `_skip_script`, `enum_values`, `_field_next`, `struct_children_ref`, `find_struct_export`, `struct_members`, `class_default_tags` |
| `values.py` | binary value decode + text render: `format_float`/`format_float_t3d`, `ValueStyle`, `_decode_struct_bin*`, `struct_tag_member_tree`, `zero_struct_tree`, `strip_member_tree`, `render_member_tree`, `member_keys`, `decode_array_tag`, `render_default_tag`, `render_object_ref`, `resolve_class_default_tags`, `resolve_class_defaults`, `resolve_type_export`, `resolve_enum_names` |

**`uedcli/propedit/`** — four concerns:

| New module | Holds |
|--------------|---
| `tokens.py` | `PropToken`, `ClassCtx`, `parse_token`, `check_hard_reject`, `check_overlaps`, `_dequote`, `_dec_finite` |
| `paths.py` | `MemberStep`, `ResolvedPath`, `resolve_path`, `_member_map`, `_text_key_ident` |
| `structtext.py` | struct-text read/write: `split_struct_text`, `emit_struct_text`, `merge_struct_texts`, `full_struct_text`, `_set_member_in_text`, `_unset_member_in_text` |
| `fields.py` | `TypedField`, `ScaleField`, `_fmt_dec` |

`Plan`, `plan_edit`, `get_lines`, `dump_all_lines`, `effective_value`, `values_match`,
`effective_match`, `zero_value`, `validate_leaf_value` and the query helpers stay in
`propedit/__init__.py` — they are the orchestration the four units serve.

**`uedcli/utexture_codec.py`** — a flat sibling, not a package, because `utexture.py` keeps its own
identity until the migration item reshapes it: `_rgb565`, `_bc_colours`, `_bc2_alpha`, `_bc3_alpha`,
`_decode_block`, `_decode_bc1`/`_bc2`/`_bc3`, `_decode_linear1`, `mip0_to_rgb`, plus `Layout`,
`DetectionFailure`, `_fitting_classes`, `detect_layout`. `utexture.py` imports from it and re-exports
the names it already exposes.

## Constraints

- **No import cycle.** `schema` → `script` → `values` is one direction only; `propedit`'s four units
  must not import the package `__init__`. Verified by a fresh-process import test, not by reading.
- **No public rename.** Anything currently reachable as `module.name` stays reachable as
  `module.name`. Renaming is a separate proposal.
- **`_`-prefixed does not mean local.** The item's own warning: grep every symbol's callers before
  moving it, including tests.
- **`dev/docs/architecture.md` names these modules and will go stale.** Editing it needs the owner's
  approval, so the build proposes the exact edits in a question file rather than making them.

## Verification

`bin/test` green with no test edited, and `test_command_isolation.py` still passing — its
heavy-import sentinels are what would catch an accidental new import edge. A green run on a host
without `cargo` proves less than it looks (`rules/tests.md`); use `bin/rust-build` so the native
tests actually run.
