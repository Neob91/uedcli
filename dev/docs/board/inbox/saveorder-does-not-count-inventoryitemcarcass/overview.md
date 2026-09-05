+++
priority = "p3"
kind = "bug"
summary = "native/saveorder.py counts the class ref inside InventoryItem but not InventoryItemCarcass, so that ref is missing from native's name/import order model."
+++

# `saveorder` does not count the `InventoryItemCarcass` class ref

`uedcli/native/saveorder.py`'s `_walk_props` counts the object/name refs carried inside `PointRegion`,
`InventoryItem`, `InitialAllianceInfo` and `SNanoKeyInitStruct`, but not `InventoryItemCarcass` —
which is byte-identically shaped to `InventoryItem` (`{class<Inventory> Inventory; int Count}`) and
appears on Island (7) and OceanLab (16) actors. Its class ref is therefore absent from native's
import/name-order model.

Invisible today because the parity gate asserts name/import table CONTENT, not order (the
owner-excluded unstable-qsort tie residual). Still a fidelity gap under the prime directive.

Found while reviewing the `InventoryItem` gate fix for NYC_Bar N=25 (opus review, 2026-09-05).

Related, same review: the gate resolves refs inside `InventoryItem`/`InventoryItemCarcass` and
`InitialAllianceInfo`, but `SNanoKeyInitStruct` (two leading name indices; 1 occurrence on UNATCO, 2
on Island, 3 on OceanLab) still falls through to the raw-bytes comparison and will produce a
conservative false FAIL once a level reaches one.
