# Spike 13 — UCC `.dx`→T3D level-export verb (C1 decision)

Probed 2026-06-18 against the live substrate (image `dx-lum-uned:latest`, UCC at
`/opt/UED22/UCC.exe`), inside an **ephemeral** container
(`docker compose run --name uned-s4a -v uned-wp-s4a:/wineprefix`, per
`dev/docs/parallel-editors.md`). Torn down after.

## DECISION: use the UCC `batchexport` verb (not the ephemeral-editor fallback)

A pure-offline UCC commandlet exports a `.dx` level to T3D and round-trips
faithfully. Adopt it for `verify.export_dx_t3d` (Task 16).

### The verb

```
wine /opt/UED22/UCC.exe batchexport <map>.dx Level T3D <outdir>
```

`ucc help batchexport` → `batchexport package.ext classname export_ext path`.
`classname=Level`, `export_ext=T3D`. The output file is named after the
**Level object**, not the package: a package `spike13.dx` writes
`<outdir>/MyLevel.T3D` (the level object is always `MyLevel`). So the caller
must read `<outdir>/MyLevel.T3D`, not `<stem>.T3D`.

### Exact run + output (verified)

`.dx` saved from a live editor (`MAP SAVE FILE=Z:\repo\Temp\spike13.dx`,
5619 bytes), containing `LevelInfo0`, builder brush, a `Light`, and a genuine
`CsgOper=CSG_Subtract` brush:

```
$ wine /opt/UED22/UCC.exe batchexport /repo/Temp/spike13.dx Level T3D "Z:\repo\Temp\uccout"
Loading package /repo/Temp/spike13.dx...
Exported Level spike13.MyLevel to Z:\repo\Temp\uccout\MyLevel.T3D
Success - 0 error(s), 0 warnings
```

Output `MyLevel.T3D` (8693 bytes) is a complete `Begin Map ... End Map` T3D with
all actors, full polygon geometry, and `CsgOper=CSG_Subtract` preserved —
structurally identical to `MAP EXPORT`. Runs headless (no editor window; pure
commandlet). No GUI, no `DISPLAY` needed.

### Round-trip / hash equivalence (verified)

Compared the UCC export against a live `MAP EXPORT` of the **same** in-memory
level via the codebase's own `parse_t3d` + `normalize_level` +
`canonical_level_hash`:

- Same actors, same `level_order`:
  `['LevelInfo0', 'Brush2', 'LightWatcher', 'Brush938']`.
- **Raw canonical hashes DIFFERED.** The *only* difference is the **package-name
  prefix** in self-referential object paths: `MAP EXPORT` (in-memory) writes
  `LevelInfo'MyLevel.LevelInfo0'` / `Brush=Model'MyLevel.Brush'`; UCC writes the
  on-disk package stem `LevelInfo'spike13.LevelInfo0'` /
  `Model'spike13.Model823'`. Geometry, props, location, order: byte-identical.
- After canonicalizing that prefix (`\w+'<pkg>\.` → `\w+'PKG.`), **the two
  hashes are IDENTICAL**:
  `48804882c4e5e126906427ab5427762e3ed7b4ed8e8f40fc9b074faec92d95fe`.

So UCC `batchexport Level T3D` is content-equivalent to `MAP EXPORT`. The
package prefix is contextual (in-memory the level object lives in package
`MyLevel`; on disk it's the file stem) and must be normalized away regardless of
which export path is used.

## Action item for Task 16 (`verify.py` / `normalize.py`)

`normalize.py` strips `Summary`/`TimeSeconds`/`Region`/`OldLocation`/`AIProfile`
(so the UCC `Summary=LevelSummary'...'` line is already handled) but does **not**
canonicalize the package prefix in `Level=` / `Brush=` object refs. Add that
canonicalization so a UCC `Level T3D` export and a live `MAP EXPORT` of the same
level hash equal. Minimal form (verified to converge the hashes above):

```python
import re
text = re.sub(r"(\w+)'([A-Za-z0-9_]+)\.", r"\1'PKG.", text)   # before parse_t3d
```

(Or canonicalize the prefix per-prop inside `normalize_actor`.)

## Note for adjacent task (4a / Task 4 predicate)

The UCC export reconfirms `Brush938` carries explicit `CsgOper=CSG_Subtract` and
the builder brush does not. **But** the builder brush here exported as `Brush2`
(this run) — not `Brush0` — which `2026-06-18-builder-brush-identification.md`
documents at length: `normalize.is_builder_brush` (`normalize.py:38`) currently
gates on `Name == "Brush0"`, which would **fail to strip** the builder brush in
the common case where the editor numbers it `Brush1+`. That predicate needs the
fix from Spike 4a (drop the exact-`Brush0` literal; key on
`Class=Brush` + no `CsgOper` + inner model name `Brush`).

## Other UCC commandlets surveyed

`ucc help` lists: `batchexport`, `checksum`, `checksumpackage`, `compress`,
`conform`, `datarip`, `decompress`, `make`, `master`, `mergedxt`, `packageflag`,
`updateumod`, etc. No `dumpint`/`exportloop` exporter. `batchexport` is the one
that produces T3D and is the right verb. The `editor.int`
`[BatchExportCommandlet]` entry corroborates (`Editor.BatchExportCommandlet`).
