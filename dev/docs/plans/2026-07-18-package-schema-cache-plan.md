# Plan — package schema cache v1 (build)

Ephemeral build plan for `dev/docs/specs/2026-07-18-package-schema-cache.md` (v1 ONLY; v2 deferred).
Once landed, the durable record lives in `architecture.md` / `decisions.md` / `unrealed/class-schema.md`.

## STEP 0 — serializer spike (DONE)
`dev/docs/spikes/2026-07-18-schema-cache-serializer/` — timed `json.loads` on the real v1 bundle
(DeusEx.u): **JSON 16.69 ms** (> the ~13 ms pickle trigger) vs **marshal 5.71 ms**. Trigger fired ⇒
**format locked = marshal** (compact stdlib binary; no pickle RCE; version drift = miss). See
`result.md`.

## STEP 1 — `config.schema_cache_root()`
Add sibling to `stub_cache_root`/`texture_images_root`: `user_cache_home() / "schema"`, `create=`
flag. (Clean file, no foreign hunks.)

## STEP 2 — `uedcli/schema_cache.py` (new)
- `SCHEMA_CACHE_VERSION: int = 1` — folded into BOTH the hashed key string AND the `v<N>/` path.
- `PackageSchema` frozen dataclass: `package_name`, `class_list`, `cmap` (cf→1-based idx),
  `super_refs` (cf→FQCN|None), `abstract` (cf→bool|None), `own_props` (cf→tuple[Prop]|None sentinel
  for a decode failure). Serialized as TWO marshal blobs — a cheap `.disc` (class list/cmap/super/abstract, what `class list` reads) + a lazily-loaded `.prop` (own-props, only for `need_props=True`), so `class list` never decodes own-props. `Prop` <-> fixed-order tuple; a `"v"` field version-checked.
  field version-checked on load. `own_props_for(class_name, owner_fqcn)` rebuilds Props with the
  caller's owner (matches `own_class_properties(..., owner_fqcn=fqcn)` exactly).
- `cache_key(realpath)` — `os.stat`; hash `f"{VER}\0{realpath}\0{size}\0{mtime_ns}"` (sha1 of ~100
  bytes, NOT the file bytes).
- `load_package_schema(path, *, name=None)` — env `off` ⇒ always `_decode(load_package)`; else
  in-process `_MEMO[realpath]` → on-disk `v<N>/<key>.bin` (corrupt/version-mismatch ⇒ miss) → miss:
  `_decode(load_package)` + `_atomic_write`. realpath keying; missing file ⇒ clean `load_package`
  SchemaError.
- `_decode(pkg)` — the existing pure producers (`iter_classes`, `class_index_map`,
  `super_fqcn_by_index`, `class_is_abstract`, `own_class_properties`); per-class super/own guarded so
  one bad class can't drop the whole package.
- `clear()` — rm `schema_cache_root()`; backs `cache clear`.
- Reuses `stub_cache._atomic_write`.

## STEP 3 — consumer rewiring (v1)
- **`classindex.ClassIndex`** — add `_schemas` field + `_schema(stem)` (cache-backed, skip-with-note
  on SchemaError, mirroring `_package`). Rewire `_cmap`, `_all_fqcns`, `is_abstract`, `children_map`
  to source per-package inputs from `_schema`. **`_package`/`ancestry` LEFT AS-IS** — `ancestry`
  carries another session's uncommitted diagnostic-print hunk; touching it would either commit or
  destroy foreign lines. So the DEFAULT `class list` tree (children_map/is_abstract/_all_fqcns/
  _cmap) is fully cached (the 6× win); `--flat`/`ancestry` still load via `_package` (follow-up).
- **`uprops.resolve_class_properties`** — schema-union path via `load_package_schema` (lazy import,
  avoids the schema_cache↔uprops cycle). Backward-compatible with a Package-seeded `_cache` (class
  show seeds `idx`-loaded Packages → stays on the live-Package branch, unchanged), so unseeded
  callers (actor prop's `_class_schema`) get the cache. Removing class show's seed to put it on the
  cache is a follow-up (blocked on the concurrent `--category` dispatch hunks).

## STEP 4 — CLI `cache clear`
New top-level `cache` group in `cli.py`; `cache clear` handler in `dispatch.py` → `schema_cache.clear()`.

## STEP 5 — tests (`test_schema_cache.py`) + harness OFF-by-default
conftest autouse `UEDCLI_SCHEMA_CACHE=off`; cache tests opt back in. Frozen-golden version guard
(marshal blob for `uned/UED22/fire.u`, committed, byte-equal to a fresh decode+serialize); same-stat
hit (spy load_package); stat-change miss; `os.utime` staleness caveat; version-bump miss; realpath
keying; corrupt=miss; parallel writers; `cache clear`; `class list` warm-vs-cold equivalence.

## STEP 6 — docs + board
architecture.md subsection + cache-shape overview; direction.md `cache/{textures,stubs}`→`schema`;
class-schema.md version-bump note; decisions.md 3-decision entry; inbox.md v2 + GC + class-show-seed
+ ancestry-cache follow-ups.
