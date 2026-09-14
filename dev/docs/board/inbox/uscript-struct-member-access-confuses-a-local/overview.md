+++
priority = "p2"
kind = "implement"
summary = "uscript: struct-member access confuses a local/param name with the field name"
+++

# uscript: struct-member access confuses a local/param name with the field name

Found building a regression fixture for the cross-package-struct-type fix, mirroring real UT99
`IpServer.UdpServerUplink.Resolved`:

```
function Resolved( IpAddr Addr )
{
    MasterServerIpAddr.Addr = Addr.Addr;
    ...
}
```

The param is named `Addr`, and `IpAddr`'s own field is ALSO named `Addr` — a real, not contrived,
UnrealScript coincidence (the fixture that isolates this, `UscIpAddrProbe`, deliberately renamed the
param to `NewTarget` to avoid it and passes `perm_gate` clean; renaming it back to `Addr` reproduces
this bug).

## Symptom

No exception — a SILENT wrong-bytes bug, only visible via `perm_gate`/`gate()` comparison against a
live UCC golden:

```
BODY function settarget.uscipaddrprobe: canonical bodies differ
  uedcli = ('obj', 'structproperty addr.uscipaddrprobe.settarget'), ...
  ucc    = ('obj', "import core.intproperty 'ipdrv.internetlink.ipaddr.addr'"), ...
```

The `StructMember` (`0x36`) token's field identity for `.Addr` resolves to the PARAM `Addr`'s own
export identity (`structproperty addr.uscipaddrprobe.settarget`) instead of the imported struct field
`IpDrv.InternetLink.IpAddr.Addr`.

## Likely mechanism (not confirmed by tracing further)

`lower.py`'s struct-member lowering (`_field_access` region, ~line 871) builds the token's `obj` part
as the bare field-name STRING (`("obj", field)`), relying on a later pass to resolve it to a real
identity. `compile._add_struct_member_import` registers the field's import under the BARE spelled
field name as the `b.imports` KEY (`b.imports.setdefault(spelled, ...)`, `spelled = field`) — not
scoped to the owning struct. Whatever resolves a token's bare-string `obj` into a final ref
(`resolve_inv`-style pass, not traced here) appears to prefer a same-name PROP (the param/local/member
`Addr`) over the struct-member import, or the import key collides with the prop's own resolution
namespace. Not root-caused to a specific line — this needs the same kind of tracing
`_register_struct_member_imports`/its final-resolution counterpart got for the final-function-import
case.

## Why not fixed in the same pass

A second, unrelated new gap (`uscript-cross-package-import-identity-collides/`) was found in the same
pass; per this session's instructions, only one small follow-on fix is in scope, and this one needs
real tracing through the token-resolution pipeline first, not a quick patch — scoped out. Doesn't block
the controlled `UscIpAddrProbe` fixture (which avoids the name collision to isolate the actual
cross-package-struct-resolution fix cleanly), but WOULD block real `IpServer` once the
`GameReplicationInfo` import-collision gap above is also fixed (`UdpServerUplink.Resolved`/
`ParseQuery`/etc. all use this exact `Addr.Addr` shape).

## Repro

Minimal: revert `uedcli/tests/fixtures/uscript/ut99/UscIpAddrProbe/UscIpAddrProbe.uc`'s param name
`NewTarget` back to `Addr` (matching real `IpServer`) and re-gate against a freshly rebuilt golden
(`ucc_compile_ut99`) — diverges as above.
