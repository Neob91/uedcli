+++
priority = "p3"
kind = "debug"
summary = "ExtendedBuilders multi-class defaultproperties timing (a third instance of the gather-order-not-recoverable-from-bytes bug)"
+++

# ExtendedBuilders multi-class defaultproperties timing

FIXED 2026-09-13. Same bug class as `uscript-name-order-enum-vs-property` and
`davesbrushbuilders-export-table-qsort-tie`, one level up: this time across a CLASS boundary, which
a single-class fixture can't exercise. `reorder._Decoder.objinputs()` only split a class's header
refs from its defaultproperties tag refs (`late_name_refs`) for `self.class_i` (first class export
by array position); the other class in a multi-class package fell through to the merged
`_class_streams` path, so its defaultproperties tag value (`GroupName="Parellelepiped"`/`"Wave"`,
both own-new) registered right after that class's header instead of after its own members.
`ordering._gather_names` also flushed `late_name_refs` in ONE trailing pass over the whole package,
deferring the FIRST class's own defaultproperties past the SECOND class's entire body — wrong, since
`compile_package_dir` compiles one class fully (through its own defaultproperties) before starting
the next.

Fix: `objinputs()` splits every class export (`e["cls"] == 0`), not just `self.class_i`;
`_gather_names` flushes each class's `late_name_refs` right before the next class object starts (or
at the end, for the last class). `Parellelepiped`/`Wave` now land at golden's exact name-table
index — `test_extendedbuilders_defaultproperties_values_land_per_class`.

`ExtendedBuilders` still fails `gate()` outright — NOT closed by this fix. The first diff moved from
name-table index 12 (`Core` vs `Vertex3f`) to index 7 (`BuildCube` vs `GetVertexCount`, both
refcount 3): this fix changed the array's own-new tail, and `msvc_qsort`'s median-of-3 pivot is
sensitive to the whole array, not just a local tied group, so a tail change shifted an unrelated
front tie's permutation. Investigated further: every name in the diverging front range genuinely
ties on refcount (verified identical between independently-decoded counts from `mine` and golden),
and the tail region it interacts with is a ~90-item refcount-0 tie (mostly never-referenced function
params/locals across both classes) — the same bug class as `DavesBrushBuilders`'s enum-tag scatter,
which `findings-ordering-re.md` already concluded needs a live `AllocateNameEntry` capture, not more
static reasoning, to pin. Not attempted (no live UED22/winedbg environment in this sandbox).

`uedcli/uscript/reorder.py` (`objinputs`), `uedcli/uscript/ordering.py` (`_gather_names`),
`uedcli/tests/test_uscript_realpkg.py`. No regression: full offline uscript suite, 223 passed
(was 222).
