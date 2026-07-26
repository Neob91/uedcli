# Partial struct/array values: import is MEMBER-WISE onto the CLASS DEFAULT (live 2026-07-18)

**Question** (spec `specs/2026-07-18-actor-prop-subcommands.md` §9): when a stored T3D property
value mentions only SOME members of a struct (`RotationRate=(Yaw=1234)`) or only some elements
of a static array (`InitialInventory(1)=…`), what do the UNMENTIONED members/elements become
when the editor imports it — the type's **zero**, or the **class default**?

**Answer: the class default.** T3D import edits member-wise onto the default-initialized
object; it never zero-fills. Confirmed live 2026-07-18 (ephemeral `dx-lum-uned` editor,
`probe.py` in this dir).

## Method

`DeusEx.Rat` was chosen via the new offline defaults decoder (`uprops.resolve_class_defaults`)
because its defaults are non-zero in exactly the right places:

- `RotationRate=(Pitch=4096,Yaw=65530,Roll=3072)` (Rotator struct, all members non-zero)
- `InitialInventory(0..2)=(Inventory=…,Count=1)` (static array of struct, `Count=1` non-zero)

Three Rats were `MAP IMPORTADD`ed into an ephemeral editor and `MAP EXPORT`ed back:

| actor | imported | exported | conclusion |
|---|---|---|---|
| RatA | `RotationRate=(Yaw=1234)` | `RotationRate=(Yaw=1234)` | Pitch/Roll stayed at the default (equal → omitted by export) |
| RatB | `RotationRate=(Pitch=4096)` — partial whose one member EQUALS the default member | **no `RotationRate` line at all** | DECISIVE: after import the whole value equals the class default ⇒ Yaw/Roll kept 65530/3072. Zero-fill would have made Yaw=0≠65530 and FORCED the line to export. |
| RatC | `InitialInventory(1)=(Count=5)` | only `InitialInventory(1)=(Count=5)` | elements 0/2 stayed at their class default (equal → omitted) — sparse arrays keep defaults for unmentioned elements |

## Consequences

- `uedcli.propedit.STRUCT_FILL = "default"`: `actor prop get`'s full-form struct rendering and
  member fall-through fill unmentioned members/elements from the class default (decoded
  offline), matching what the built map will actually contain.
- `unset KEY.Member` (removing a member from a stored value) therefore reverts that member to
  the **class default**, not to zero — only `unset KEY` (whole prop) and a member's absence
  both mean "class default", consistently.
- **Export is member-precise default-diffing**: `MAP EXPORT` omits a whole property equal to
  the class default AND omits individual struct members equal to the default member. This is
  the exact mechanism behind the open p2 item "materialize post-verify fails when the trunk
  stores a prop equal to its class default" (board/inbox.md) — now pinned to member
  granularity.

Recorded in `unrealed/t3d.md` ("Partial struct/array property values"). Probe harness:
`probe.py` (committed here); raw export in `_scratch/probe_export.t3d` (throwaway).
