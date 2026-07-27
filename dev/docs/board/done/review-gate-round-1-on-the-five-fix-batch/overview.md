+++
priority = "p?"
kind = "unknown"
summary = "Review-gate round 1 on the five-fix batch — resolved 2026-07-25"
+++

# Review-gate round 1 on the five-fix batch — resolved 2026-07-25

Two cold reviewers over
`432e65163..`: the biggest finding was that the `map_save` docs justified the structural check with
a save mechanism this editor does not use — `UObject::SavePackage` writes `Save.tmp`, rewrites the
header LAST inside it, and then MOVES it onto the target (📖 `core.dll` strings, now a documented
UnrealEd fact in `unrealed/commands.md` + `spikes/2026-07-25-map-save-mechanism/`). **Round 2's own
follow-up correction, recorded here because this entry first got it wrong too:** whether that move
is a rename or a byte COPY is NOT determined — `core.dll` imports no `ReadFile` either, so its file
I/O bypasses the import table entirely and the missing `MoveFile*` proves nothing. The check stands
as insurance; the rationale, `architecture.md`, the `map_save` docstring and the `decisions.md`
entry were corrected, and `commands.md`'s "truncated `Leaves` array" example was retracted (spike
§91 disproved it). Also: `settle`/`stable_reads`, the per-probe `timeout=`,
the elapsed-time message, the empty-file guard, the offset lower bound, the probe scripts and the
magic-vs-`upackage` parity are now each pinned by a test (11 mutations applied to `driver.py`, all
11 caught, none before); `container_stat`/`container_file_head` no longer collapse a `stat`/`od`
FAILURE into "not there"; `brush scale --pivot-actor` resolves its actor before the class resolver
too; `test_real_class_hierarchy_decides_mover_ness` now covers the case-sensitivity half of the
re-measurement; the `build_ued_golden` harness dropped its own retired size-only wait; and
`test_qualify`'s hand-rolled canonicalization loop is deleted (covered by `test_movers` +
`test_prefab_migration`). Three findings deferred to `inbox.md` with detail: the remaining unbounded
`docker exec` calls (count corrected to 8 across 6 methods + `xfer.py`), the missing `map_save`
integration test, and the `Save.tmp` collision/leftover.
