# Spec — migrate `utexture.py` + `dxpkg.py` onto the `upackage.py` core

## Goal

Delete the two private copies of the UE1 low-level package parser (`utexture.py`, `dxpkg.py`) and
have both build on the single canonical reader `upackage.py`, per `direction/packages.md` ("exactly
one low-level reader … No use-case and no file extension reimplements the low-level parsing"). Chore,
not a feature: no observable CLI change, byte-identical decode results. Both are byte-validated
decoders, so this is a deliberate separate pass with corpus revalidation — never folded into a feature
change (`packages.md` Rejected: "Migrating every decoder onto the core in the change that introduced
it").

## Current state — three parsers of the same wire format

`upackage.py` (313 lines) is the canonical core: `read_compact_index`, `read_fstring`,
`read_array_index`, `Package` + `load_package`/`_parse_package` (header + name/import/export tables,
outer-chain qualification), `PropertyTag` + `read_property_tags` (the tagged-property list, raw value
spans). Raises `SchemaError` (a `ValueError` subclass).

`utexture.py` (1090 lines) — duplicates and adds texture decode:
- `_ci` (`:38`) = `read_compact_index`.
- `Package` (`:54`) = a non-frozen twin of `upackage.Package`, plus convenience `name()`,
  `name_of_ref()`, `class_of_export()`.
- `load_package` (`:89`) = `_parse_package` **plus a DoS guard** (`:110`): every declared table count
  is bounded by file size before any entry is read (a header claiming 4 billion names otherwise walks
  for >200 s). Raises plain `ValueError`, not `SchemaError`.
- `_read_props` (`:159`) = `read_property_tags` but **returns decoded values** (`name -> (ptype,
  value)`), decoding byte/int/float/object/name inline.
- Texture-specific (KEEP, they are the reason this file exists): `Mip`, `TextureObj`,
  `decode_texture`, `decode_palette`, `mip0_to_rgb`, the BC1/BC2/BC3 decoders, `detect_layout`/
  `Layout`, `DecodedTexture`, `TextureResolver`.

`dxpkg.py` (247 lines) — duplicates header+import parsing only:
- `_read_compact_index` (`:40`) = `read_compact_index`.
- `PackageHeader`/`parse_header`/`_parse_header` (`:99`) = a names+imports-only `load_package`, with a
  **version allowlist** `(61, 68, 69)` and "refusing to guess offsets for an unverified version".
- `_read_name` (`:74`) decodes **negative-length UTF-16LE** name entries (DeusEx Unicode Group names,
  e.g. `20_AireGardens.dx`); `_read_name_v61` handles the ver<64 null-terminated form.
- `direct_packages`/`transitive_closure` — the import-closure extractor used by `store_export`/
  `verify`/`packages`. KEEP; only its parser internals migrate.

## The delta to reconcile — what the core is missing

Three real behavioral differences the private copies carry that `upackage` does **not**, and must gain
before the migration is byte-safe:

1. **Negative-length UTF-16 name entries.** `upackage.read_fstring` (`upackage.py:56`) rejects a
   negative length (`if length < 0 … raise SchemaError`). `dxpkg._read_name` decodes it as UTF-16LE.
   The DX map corpus contains these (Unicode Group names). **Migrating `dxpkg` onto `upackage` without
   teaching the core the negative-length form silently breaks parsing of every Unicode-named package.**
   Fix: extend the core's name-table reader to decode `length < 0` as UTF-16LE of `-length` code units.
   Note `read_fstring` (the generic FString reader) and the *name-table* reader may want to stay
   distinct — the negative-length convention is a name-table fact; check whether any other
   `read_fstring` caller should also accept it (likely not).

2. **The DoS count-bound guard.** `utexture.load_package` bounds `namecnt`/`impcnt`/`expcnt` by file
   size before looping. `upackage._parse_package` has no such bound — it relies on the eventual
   export-overrun check, but a 4-billion `namecnt` loops in the name phase first. **Port this guard
   into `upackage.load_package`** so the whole tool gains it; it is a strict, format-derived lower
   bound no valid package can trip.

3. **The version allowlist.** `dxpkg._parse_header` refuses versions outside `(61, 68, 69)`.
   `upackage.load_package` accepts any version (it only branches ver<64 vs >=64 for the name table).
   Decide whether to keep the allowlist (see Open questions). If kept, it becomes a thin check in
   `dxpkg` after `upackage.load_package` returns (`Package.version`), not a change to the core.

Smaller, non-blocking notes:
- `upackage.load_package` parses the **full export table** (integrity: must not overrun EOF), which
  `dxpkg` skips. Harmless for `dxpkg` (it only reads names+imports afterward) and strictly more
  checking; the trailing-padding tolerance is already in the core (`upackage.py:233-240`).
- `upackage.Package` lacks `utexture.Package`'s `name()` and `class_of_export()` convenience methods.
  Either add them to the core (thin, total, None-on-OOR — consistent with the existing helpers) or
  inline at the call sites. `name_of_ref` already exists with matching semantics.
- Error type: `utexture` callers catch plain `ValueError`; `SchemaError` subclasses `ValueError`, so
  they keep working (same pattern `dxpkg` already relies on, `dxpkg.py:16`).
- `read_property_tags` returns raw spans; `utexture._read_props` returns decoded values. The migration
  replaces `_read_props` with `read_property_tags` + a small value-decode helper (byte/int/float/
  object-ref/name) applied to `PropertyTag.raw`, feeding `utexture`'s existing consumers
  (`_class_defaults`, `_effective_flag`, `decode_texture`'s prop reads).

## Design — the migration passes

1. **Core additions first (own commit):** negative-length UTF-16 name decode + DoS count-bound guard
   in `upackage`, each with a regression test (a synthetic Unicode-name package; a header with an
   absurd count). No caller change yet — the core is a superset.
2. **`dxpkg` onto the core:** drop `_read_compact_index`/`_read_name*`/`PackageHeader`/`parse_header`/
   `_parse_header`; `direct_packages` calls `upackage.load_package(path)` and walks `pkg.imports`
   (identical `(cp,cn,pi,on)` tuple) — `upackage.import_package_of` already does the outer-chain walk,
   so `direct_packages` becomes a set comprehension over it. Keep `transitive_closure`,
   `_find_package_file`, and (if retained) the version allowlist as a post-load check.
3. **`utexture` onto the core:** drop `_ci`/`Package`/`load_package`/`_read_props`; import
   `upackage.Package`/`load_package`/`read_property_tags`; add the value-decode helper. All texture
   decode stays. Adapt the `TextureResolver` exception handling (already catches `ValueError` broadly).
4. **Revalidate** against the full texture corpus + closure oracles (below) before merge.

Keep it tight: this is deletion + rewiring, not a redesign. No new decode behavior, no CLI surface.

## Edge cases & risks

- **Unicode name regression (highest risk).** Without core delta #1, content/map packages with Unicode
  Group names fail to parse — caught only if the corpus test includes one. Pin `20_AireGardens.dx`
  (or the smallest Unicode-name fixture) explicitly.
- **v61 packages** (`CoreTexDetail`/`CoreTexWater`/`Palettes`/`Render`/`TITAN`): the core's ver<64
  name reader (`upackage.py:203`) already handles the null-terminated form; confirm against these five.
- **Lost version allowlist** if not re-added — an unverified version would be parsed with guessed
  offsets rather than refused. Owner/impl call (Open questions).
- **DoS guard placement:** must land in the core, not just be dropped with `utexture`'s copy, or the
  whole tool loses protection it currently has on the texture path.
- **`trailing_bytes`/integrity semantics** in `TextureObj` are computed in the texture-decode layer,
  not the header parser — untouched by this migration; confirm no reliance on `utexture.load_package`'s
  exact cursor behavior.

## Tests

- Existing corpus suites must stay green unchanged: `tests/test_utexture_corpus.py`,
  `test_utexture_corpus_installs.py`, `test_utexture_blocks.py`, `test_utexture_layout.py`,
  `test_dxpkg.py`, `test_stub.py` (closure).
- New core regressions: a Unicode-name package parses (delta #1); an absurd-count header raises
  `SchemaError` fast (delta #2); v61 fixture parses via the core.
- A parity test asserting `dxpkg.direct_packages` and `utexture.load_package` over the corpus produce
  identical results before/after (guard against a silent decode drift) — this is the "byte-validated
  revalidation" the item calls for.

## Open questions

- Keep `dxpkg`'s `(61,68,69)` version allowlist as a post-load check, or let the core accept any
  version whose table layout it can read? See `questions/keep-version-allowlist.md`. (An
  implementation call more than a product one, but it changes what input is refused, so surface it.)
