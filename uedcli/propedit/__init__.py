"""`actor prop set|unset|get` — the pure verb logic: dot-path grammar, whole-value vs
targeted-edit planning, effective-value reads (stored → class default → type zero), dump-all,
and the `find --prop` effective-value matcher.

Spec in board item `materialize-post-verify-fails-when-the-trunk`; direction/packages.md 2026-07-18 10:02 +
10:30 UTC. Everything here is model-side and schema-driven; the class schema / defaults /
struct-member / enum lookups arrive through a lazy `ClassCtx` bundle so that tokens which never
need the schema (hard-rejects, typed-field-only invocations) run without the v68 install
(spec §2.4), and `cli.resources` owns the FOUR seams (`class_schema` / `class_defaults` /
`struct_members` / `enum_names`) that tests mock.

Grammar (spec §3):
    TOKEN   := KEY [PATH] ("=" VALUE)?
    PATH    := ("." SEGMENT)+
    SEGMENT := decimal integer (array index) | identifier (struct member)
An index segment may index the base prop (`MultiSkins.2`) or a STRUCT MEMBER that is itself a
static array (`Nest.Marks.1` — stored/rendered as `Marks(1)=` inside the struct text). The T3D
`KEY(N)` spelling is rejected with a hint; the STORED T3D keeps its native `Key(N)=` form (this
is CLI grammar only).

Module map — six layers, each importing only the ones above it:

- `base.py` — the error, the hard-reject set, the regexes, `ClassCtx`.
- `tokens.py` — the token grammar and the whole-invocation checks.
- `paths.py` — a token's dot path resolved against the class schema.
- `structtext.py` — reading and writing a T3D struct literal.
- `fields.py` — the typed-field registry (`Location`, `MainScale`/`PostScale`).
- `edit.py` — the plan/get/dump/match orchestration.

This file is pure re-export; every symbol below still resolves as `propedit.X`.
"""
from .base import (                                  # noqa: F401
    ClassCtx,
    HARD_REJECT,
    PropEditError,
    STRUCT_FILL,
    _IDENT_RE,
    _INT_RE,
    _NUM_BOUND,
    _PAREN_ANY_RE,
    _PAREN_KEY_RE,
    _VR_STRUCTS,
    _dec_finite,
    _dequote,
)
from .tokens import (                                # noqa: F401
    PropToken,
    check_hard_reject,
    check_overlaps,
    parse_token,
)
from .paths import (                                 # noqa: F401
    MemberStep,
    ResolvedPath,
    _member_map,
    _text_key_ident,
    resolve_path,
)
from .structtext import (                            # noqa: F401
    _maybe_comma_sugar,
    _set_member_in_text,
    _unset_member_in_text,
    emit_struct_text,
    full_struct_text,
    merge_struct_texts,
    split_struct_text,
    zero_value,
)
from .fields import (                                # noqa: F401
    ScaleField,
    TYPED_FIELDS,
    TypedField,
    _fmt_dec,
)
from .edit import (                                  # noqa: F401
    Plan,
    _canon_scalar,
    _canonicalize_enum,
    _stored_map,
    _validate_query_value,
    dump_all_lines,
    effective_match,
    effective_value,
    get_lines,
    plan_edit,
    validate_leaf_value,
    values_match,
)
