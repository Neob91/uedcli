+++
priority = "p2"
kind = "implement"
summary = "Shared Rust core for class-schema resolution: native + WASM"
+++

# Shared Rust core for class-schema resolution: native + WASM

Built via a 21-round plan review then a 10-task subagent-driven-development build (Task 4 split
into 6 sub-parts). New `resolve-core` (native, PyO3-consumed) and `resolve-wasm` (browser)
crates implement `resolve_class`/`resolve_actor_props` once, replacing `effective_props.py`'s
walk for the Inspector-props path. Golden fixture (`uedcli/tests/fixtures/resolve_golden/`)
round-trips native and WASM output against the same corpus data.

Two real bugs were found and fixed during the build, independently verified before merging:
a `collect_struct_type` cycle guard gap (unbounded recursion on a self-referential struct member,
not `sup`), and the golden/native path silently dropping `Location`/`MainScale`/`PostScale` from
every actor entry (fixed by reusing `effective_props._resolve_typed_fields`).

Final whole-branch review: "Ready to merge: Yes with minor fixes." Fix wave applied, scoped
re-review confirmed READY TO MERGE, no new breakage.

Follow-up filed: `dev/docs/board/inbox/architecture-md-stale-on-the-new-resolve-core/` (the
architecture doc doesn't yet describe the 3-crate workspace split).
