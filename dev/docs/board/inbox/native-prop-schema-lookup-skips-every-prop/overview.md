+++
priority = "p2"
kind = "debug"
summary = "Native prop-schema lookup skips every prop on a BARE trunk class (9 355 warnings on UNATCO); closing it surfaces a `MyLevel` local-object-ref import defect (§88)"
+++

# Native prop-schema lookup skips every prop on a BARE trunk class (9 355 warnings on UNATCO); closing it surfaces a `MyLevel` local-object-ref import defect (§88)

`default_schema_
lookup` early-returns `{}` for any unqualified class (`"." not in fqcn`), and real-level trunks
store bare classes (`AllianceTrigger`), so ALL typed props are dropped ("not in class schema
(skipped)"). Qualifying the bare class for the schema lookup (via `pkgref.build_class_package_
index`, already built for the import fix) closes the warnings — BUT then object-property values
that reference sibling actors (`Region.Zone=LevelInfo'MyLevel.LevelInfo0'`, `Base=`, mover
markers, AmbientSound refs) emit a bogus **`MyLevel` PACKAGE import**, and the game fails the load
with `Can't find file for package 'MyLevel'`. Intra-level object refs must resolve to the target
actor's LOCAL export ref, not a package import (cf. the `Brush=Model'MyLevel.<shape>'` drop
`materialize._trunk_to_actorspecs` already does). Fix both together: qualify-for-schema AND
resolve local object-property refs to export refs. (Tried + reverted 2026-07-19 — the class-import
fix landed without it.)
