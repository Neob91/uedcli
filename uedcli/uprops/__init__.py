"""Offline class-property extraction from a UE1 `.u` package's bytes — the schema source for
`actor prop` validation (decisions 2026-06-26 12:41/14:10 UTC: no fallbacks; parse the REAL game
`.u`, never a v69 stub). Productionizes the `2026-06-26-uproperty-typed-decode` spike
(`uproperty_decode.py`), adding the **Super-chain inheritance union across packages** the spike's
own-props-only `class_properties` lacked.

For each `*Property` export whose `Outer` is a class it recovers `name`, `kind`, `array_dim`
(static-array bound, 1 for a scalar), the low-16 `CPF_*` flags, and the type tail (the body's final
compact): a `ByteProperty`'s Enum (→ its value names), an `Object`/`Class`/`Struct`Property's
referenced object. `resolve_class_properties` then unions a class's own props with every ancestor's,
crossing package boundaries via the import table and a caller-supplied `resolver` (package name →
`.u` path on the schema search path). Child props override parents on a case-folded name collision.

Pure: parses bytes, never runs the editor. The low-level container parsing (header, tables,
compact index, tagged-property lists) lives in the unified core `upackage.py` (direction/packages.md
2026-07-18 10:02 §5) — `Package`/`load_package`/`SchemaError` are re-exported from there, so
every existing `uprops.Package`/`uprops.SchemaError` caller keeps working unchanged. The
cursor-to-EOF integrity check on every record is the no-fallback contract — a layout error
desyncs and is caught.

Module map — four layers, each importing only the ones LISTED BEFORE it:

- `base.py` — `Prop`, the UProperty kind sets, the `SchemaError` guard.
- `ufield.py` — the UField family: property/enum/struct decode and the bytecode walk.
- `uclass.py` — the UClass level: export index, own props, the Super chain, `abstract`, defaults
  block.
- `values.py` — value decode, render and the rendering policy (`ValueStyle`), plus the
  hierarchy-walking defaults resolution.

This file is pure re-export; every symbol below still resolves as `uprops.X`, and each submodule
reaches `upackage` directly rather than through this root.
"""
from ..upackage import (                             # noqa: F401  (re-exported public API)
    Package,
    PropertyTag,
    SchemaError,
    load_package,
    read_compact_index as _read_compact_index,
    read_fstring as _read_fstring,
    read_property_tags,
    PT_BYTE, PT_INT, PT_BOOL, PT_FLOAT, PT_OBJECT, PT_NAME, PT_STR_LEGACY, PT_STR, PT_STRUCT,
)
from .base import (                                  # noqa: F401
    CPF_NET,
    PROPERTY_TYPES,
    Prop,
    _KINDS_WITH_TYPE_REF,
    _STRUCT_BIN_SIZES,
    _last_compact,
    _safe_name,
    _schema_guard,
)
from .ufield import (                                # noqa: F401
    _EX_END_FUNCTION_PARMS,
    _decode_property,
    _field_next,
    _skip_script,
    _walk_expr,
    enum_values,
    find_struct_export,
    struct_children_ref,
    struct_members,
)
from .uclass import (                                # noqa: F401
    _ABSTRACT_DECL,
    _ABSTRACT_KW,
    _BLOCK_COMMENT,
    _LINE_COMMENT,
    _class_script_source,
    _super_fqcn,
    abstract_from_source,
    class_default_tags,
    class_export_index,
    class_index_map,
    class_is_abstract,
    iter_classes,
    own_class_properties,
    resolve_class_properties,
    super_fqcn,
    super_fqcn_by_index,
)
from .values import (                                # noqa: F401
    CLI_STYLE,
    T3D_STYLE,
    ValueStyle,
    _byte_member_text,
    _decode_struct_bin,
    _decode_struct_bin_at,
    _pkg_for_owner,
    _struct_tree_at,
    _zero_member_text,
    decode_array_tag,
    format_float,
    format_float_t3d,
    member_keys,
    render_default_tag,
    render_member_tree,
    render_object_ref,
    resolve_class_default_tags,
    resolve_class_defaults,
    resolve_enum_names,
    resolve_type_export,
    strip_member_tree,
    struct_member_schema,
    struct_tag_member_tree,
    zero_struct_tree,
)
