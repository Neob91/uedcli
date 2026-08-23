# Update the two owner-gated docs for the god-module split

## Context

This item split `uedcli/uprops.py` and `uedcli/propedit.py` into packages. Nothing was renamed and
nothing changed behaviour: every `uprops.X` / `propedit.X` still resolves through the package root.
What goes stale is the FILE each doc names.

`dev/docs/rationale/` is agent-owned and was updated in the same change. These two are not, so the
exact rows are proposed here rather than applied (`CLAUDE.md`, "dev/docs — never edit without the
owner's approval, except the board"). Nothing reddens while this waits — every citation below is
inline code, which `test_doc_links.py` strips before matching.

The new layouts:

- `uedcli/uprops/` — `base` < `ufield` < `uclass` < `values`, plus a re-export-only `__init__.py`.
- `uedcli/propedit/` — `base` < `tokens` < `paths` < `structtext` < `fields` < `edit`, same root.

The `utexture.py` decoder split is NOT part of this — it is blocked on a name collision, tracked as
`utexture-decode-py-collides-with-the-2026-06-27`. No doc row below depends on it.

## Proposed edits — `dev/docs/architecture.md`

| Line | Now | Proposed |
|------|------------------------------------------|---
| 148 | `uprops.py` (offline class-property SCHEMA + class-DEFAULT extraction …) | `uprops/` (same text; add "four layers — `base` < `ufield` < `uclass` < `values` — behind a re-export-only root") |
| 150 | `propedit.py` (the pure `actor prop set/unset/get` verb logic: …) | `propedit/` (same text; add "six layers — `base` < `tokens` < `paths` < `structtext` < `fields` < `edit` — behind a re-export-only root") |
| 152 | "Its `split_struct_text` does NOT re-implement the struct-literal grammar" | "Its `structtext.split_struct_text` does NOT re-implement the struct-literal grammar" |
| 1149 | heading "… the `actor prop` verbs (`upackage.py`, `uprops.py`, `propedit.py`)" | "… the `actor prop` verbs (`upackage.py`, `uprops/`, `propedit/`)" — no doc cites this anchor, checked |
| 1191 | "`propedit.py` is the pure verb logic" | "`propedit/` is the pure verb logic" |
| 1204 | "`uprops.py` builds on it" | "`uprops/` builds on it" |

## Proposed edit — `dev/docs/unrealed/class-schema.md`

| Line | Now | Proposed |
|------|------------------------------------------|---
| 4 | "Consumed by `uedcli/uprops.py` (`class_is_abstract`, `_class_script_source`)" | "Consumed by `uedcli/uprops/uclass.py` (`class_is_abstract`, `_class_script_source`)" |

Both symbols live in `uclass.py` and both still resolve as `uprops.class_is_abstract` /
`uprops._class_script_source`.

## Answer

<!-- Empty = open. Write the decision here. -->
