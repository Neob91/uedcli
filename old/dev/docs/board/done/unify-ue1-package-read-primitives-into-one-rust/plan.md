# Unify UE1 package read primitives into one Rust core — PR1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `upackage.py`'s header/name/import/export table decode (the profiled 61M-call hot
loop) to Rust, exposed via the existing `uedcli_native` PyO3 extension, with a two-tier cache —
without changing `upackage.py`'s public API or breaking any of its ~20 existing importing files.

**Architecture:** New pure-Rust module `uedcli-native/src/package_read.rs` (no PyO3 inside,
`cargo test`-able standalone, matching `model_read.rs`'s style) implements the byte-level decode.
Two new `#[pyfunction]`s in `lib.rs` expose it. `upackage.py` becomes a thin shell: its dataclasses
and public functions keep their names/signatures, but their bodies call into Rust instead of
looping in Python. A new `Package.name_entries` field and `NameEntry` dataclass carry information
(`gate.py`'s per-name flags/offsets) nothing currently uses; `Package.names` itself is untouched.
Two cache tiers (in-process dict, on-disk `marshal` blobs mirroring `schema_cache.py`) sit inside
`load_package`.

**Tech Stack:** Rust (PyO3 0.22, `uedcli-native` crate), Python 3.12 (`uedcli/upackage.py` +
callers), `cargo test` + `pytest`.

**Spec:** `dev/docs/board/to-plan/unify-ue1-package-read-primitives-into-one-rust/spec.md`
(read it — this plan implements it, with two corrections found during planning, both already
folded into the spec: the `Package.names`/`NameEntry` design, and a `RawPackage.imports` type fix).

## Global Constraints

- **No CLI-observable change.** Byte-identical decode results to today's Python; zero new/changed
  CLI flags, output, or error text visible to a user.
- **`upackage.py`'s public API is frozen**: `Package` (same existing fields + additions, never
  removed/renamed), `load_package`, `parse_package_bytes`, `_parse_package`, `read_property_tags`,
  `name_of_ref`/`object_path`/`object_class_name`/`import_package_of`, `SchemaError`,
  `read_compact_index`, `read_fstring`, `read_array_index`. Every existing caller keeps working
  with **zero changes** — this plan does not touch any of the ~20 files that import from
  `upackage.py` (that's PR2's job, retiring the *other* duplicate parsers onto this core — a
  separate, later plan).
- **`Package.names` stays `list[str]`, unchanged.** Do not merge it into tuples (see spec's
  "Revised during planning" note — a real, measured caller-blast-radius finding, not a style
  choice).
- **No new crate dependency.** Hand-roll byte decoding in `package_read.rs`, matching
  `model_read.rs`/`model_write.rs`'s existing style — no `byteorder`/`nom`.
- **Decode correctness proven against independent oracles** (`direction/packages.md`): the
  before/after parity test (Task 8) compares Rust's output against the *existing, currently-shipped*
  Python decoder on real files — never against a fixture this change's own Rust encoder produced
  (there is no Rust encoder here; this is read-only).
- **Every parse error stays a named `SchemaError`** in Python — a malformed package must never
  surface a bare Rust panic or an untyped exception to a caller.
- Run tests via `bin/test`, never bare `pytest` (`dev/docs/rules/tests.md`). On this host, use
  `-s` and a worktree-relative `TMPDIR` (see `USCRIPT-COMPILER.md`'s testing note) —
  `mkdir -p _scratch/pt && TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s <args>`.
  Scope every run to what the task touches; run the full non-integration suite once, before the
  final commit of this plan (Task 9).

---

### Task 1: Rust byte-cursor primitives

**Files:**
- Create: `uedcli-native/src/package_read.rs`
- Modify: `uedcli-native/src/lib.rs:1-10` (add `mod package_read;` near the other `mod` declarations)

**Interfaces:**
- Produces: `pub fn read_compact_index(buf: &[u8], pos: usize) -> Result<(i64, usize), BuildError>`,
  `pub fn read_name(buf: &[u8], pos: usize, version: u16) -> Result<(String, u32, usize), BuildError>`
  (returns `(text, flags, next_pos)`), `pub fn read_fstring(buf: &[u8], pos: usize) -> Result<(String, usize), BuildError>`,
  `pub fn read_array_index(buf: &[u8], pos: usize) -> Result<(i64, usize), BuildError>`.
- Consumes: `crate::model::BuildError` (the crate's existing error type — reuse it, don't invent a
  new one; matches `model_read.rs`'s own pattern of `Result<_, BuildError>` with a `what: &str`
  naming the field in the message).

These four functions are faithful ports of `uedcli/upackage.py`'s `read_compact_index` (line 40),
`read_fstring` (line 56), `read_array_index` (line 66), and the `read_name` closure inside
`_parse_package` (line 208) — **plus** `dxpkg.py`'s `_read_name`'s negative-length-is-UTF-16LE
branch (line 74), which `upackage.py` currently lacks (it rejects negative length). This is the
"file describes itself" unification the spec calls for: one decoder, no per-game branch, the
length's sign is a wire fact.

- [ ] **Step 1: Write the module skeleton + `read_compact_index` with its test**

Create `uedcli-native/src/package_read.rs`:

```rust
//! One Rust decoder for the UE1 package wire format (header + name/import/export tables, tagged
//! properties) — replaces `uedcli/upackage.py`'s pure-Python hot loop (61M `read_compact_index`
//! calls profiled rendering one `IsvKran32.unr` photo). Read path only: the write path
//! (`native/codec.py`, `native/pkg_write.py`'s encoder) and the `UModel` BSP-body codec
//! (`model_read.rs`/`model_write.rs`) are separate and untouched.
//!
//! Faithful port of `uedcli/upackage.py`'s decoders, plus `dxpkg.py`'s negative-length-is-UTF-16LE
//! name decode (a real wire feature `upackage.py` currently rejects) — one decoder, no per-game
//! branch. See `dev/docs/board/to-plan/unify-ue1-package-read-primitives-into-one-rust/spec.md`.

use crate::model::BuildError;

/// FCompactIndex: signed, variable-length (UE1). Mirrors `upackage.read_compact_index` exactly,
/// including its continuation-shift schedule (breaks after the byte at shift>=27, so at most 5
/// bytes / 34 bits of magnitude before the sign).
pub fn read_compact_index(buf: &[u8], pos: usize) -> Result<(i64, usize), BuildError> {
    let mut pos = pos;
    let b0 = *buf.get(pos).ok_or_else(|| {
        BuildError(format!("compact index: buffer overrun at byte {pos}"))
    })?;
    pos += 1;
    let neg = b0 & 0x80 != 0;
    let mut val: i64 = (b0 & 0x3F) as i64;
    if b0 & 0x40 != 0 {
        let mut shift: u32 = 6;
        loop {
            let b = *buf.get(pos).ok_or_else(|| {
                BuildError(format!("compact index: buffer overrun at byte {pos}"))
            })?;
            pos += 1;
            val |= ((b & 0x7F) as i64) << shift;
            if b & 0x80 == 0 || shift >= 27 {
                break;
            }
            shift += 7;
        }
    }
    Ok((if neg { -val } else { val }, pos))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compact_index_round_trips_small_values() {
        // Single-byte form: bit6 clear, value in bits 0-5, sign in bit7.
        assert_eq!(read_compact_index(&[0x05], 0).unwrap(), (5, 1));
        assert_eq!(read_compact_index(&[0x85], 0).unwrap(), (-5, 1));
        assert_eq!(read_compact_index(&[0x00], 0).unwrap(), (0, 1));
    }

    #[test]
    fn compact_index_round_trips_multi_byte_values() {
        // bit6 set = continuation. 0x41 (0100_0001) then 0x02 (no continuation): val = 1 | (2<<6) = 129.
        assert_eq!(read_compact_index(&[0x41, 0x02], 0).unwrap(), (129, 2));
        // Same magnitude, negative (bit7 set on the first byte too): 0xC1, 0x02.
        assert_eq!(read_compact_index(&[0xC1, 0x02], 0).unwrap(), (-129, 2));
    }

    #[test]
    fn compact_index_overrun_names_the_byte() {
        let err = read_compact_index(&[0x40], 0).unwrap_err();
        assert!(err.0.contains("byte 1"), "message: {}", err.0);
    }
}
```

- [ ] **Step 2: Run the new tests to verify they pass**

Run: `cd uedcli-native && cargo test package_read -- --nocapture`
Expected: 3 tests pass (`compact_index_round_trips_small_values`,
`compact_index_round_trips_multi_byte_values`, `compact_index_overrun_names_the_byte`).

If `cargo test` isn't directly runnable in this environment, use `bin/_venv.sh`'s cargo-test path
(same one `bin/test` invokes) — check `bin/_venv.sh` for the exact `run_cargo_test` invocation
first; don't invent a different build path.

- [ ] **Step 3: Add `read_fstring`, `read_array_index`, and `read_name` (with the UTF-16LE branch)**

Append to `package_read.rs` (after `read_compact_index`, before the `#[cfg(test)]` block):

```rust
fn latin1_decode(bytes: &[u8]) -> String {
    bytes.iter().map(|&b| b as char).collect()
}

/// A v>=64 generic FString: compact byte length (including the terminating NUL), latin-1 bytes.
/// Mirrors `upackage.read_fstring` — unlike `read_name` below, a negative length here is always
/// an error (the negative-length-is-UTF-16 convention is a NAME-TABLE fact, not proven true of
/// every FString caller — see the spec's design notes).
pub fn read_fstring(buf: &[u8], pos: usize) -> Result<(String, usize), BuildError> {
    let (length, pos) = read_compact_index(buf, pos)?;
    if length < 0 || pos + length as usize > buf.len() {
        return Err(BuildError(format!("FString overruns buffer (len={length} at {pos})")));
    }
    let raw = &buf[pos..pos + length as usize];
    let cut = raw.iter().position(|&b| b == 0).unwrap_or(raw.len());
    Ok((latin1_decode(&raw[..cut]), pos + length as usize))
}

/// A property tag's static-array element index. Mirrors `upackage.read_array_index`'s packed
/// 1/2/4-byte form exactly.
pub fn read_array_index(buf: &[u8], pos: usize) -> Result<(i64, usize), BuildError> {
    let b0 = *buf.get(pos).ok_or_else(|| {
        BuildError(format!("array index: buffer overrun at byte {pos}"))
    })?;
    if b0 < 0x80 {
        return Ok((b0 as i64, pos + 1));
    }
    let need = if (b0 & 0xC0) == 0x80 { 2 } else { 4 };
    if pos + need > buf.len() {
        return Err(BuildError(format!("array index: buffer overrun at byte {pos}")));
    }
    if (b0 & 0xC0) == 0x80 {
        Ok((((b0 & 0x3F) as i64) << 8 | buf[pos + 1] as i64, pos + 2))
    } else {
        Ok(((((b0 & 0x3F) as i64) << 24)
            | ((buf[pos + 1] as i64) << 16)
            | ((buf[pos + 2] as i64) << 8)
            | (buf[pos + 3] as i64), pos + 4))
    }
}

/// A name-table entry: text + the per-entry flags u32 the wire format always stores alongside it.
/// ver<64: null-terminated latin-1 string + u32 flags (no length prefix).
/// ver>=64: compact-index length (NEGATIVE = UTF-16LE of `-length` code units — DeusEx Unicode
/// group names, e.g. `20_AireGardens.dx`; POSITIVE = latin-1, both null-terminated within their
/// declared byte span) + u32 flags. Faithful port of `upackage.py`'s `read_name` closure (line 208)
/// merged with `dxpkg.py`'s `_read_name` (line 74) — the negative-length branch `upackage.py`
/// currently lacks.
pub fn read_name(buf: &[u8], pos: usize, version: u16) -> Result<(String, u32, usize), BuildError> {
    if version < 64 {
        let end = buf[pos..]
            .iter()
            .position(|&b| b == 0)
            .map(|i| pos + i)
            .ok_or_else(|| BuildError(format!("name entry at {pos}: no terminating NUL")))?;
        if end + 1 + 4 > buf.len() {
            return Err(BuildError(format!(
                "name entry at {pos} is missing its 4 trailing flags bytes"
            )));
        }
        let text = latin1_decode(&buf[pos..end]);
        let flags = u32::from_le_bytes(buf[end + 1..end + 5].try_into().unwrap());
        return Ok((text, flags, end + 1 + 4));
    }
    let (length, pos) = read_compact_index(buf, pos)?;
    let nbytes: usize = if length < 0 { (-length) as usize * 2 } else { length as usize };
    if pos + nbytes + 4 > buf.len() {
        return Err(BuildError(format!(
            "name entry at {pos} overruns buffer (len={length}, size={})",
            buf.len()
        )));
    }
    let raw = &buf[pos..pos + nbytes];
    let text = if length < 0 {
        let units: Vec<u16> = raw
            .chunks_exact(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]))
            .collect();
        let s = String::from_utf16_lossy(&units);
        s.split('\u{0}').next().unwrap_or("").to_string()
    } else {
        let cut = raw.iter().position(|&b| b == 0).unwrap_or(raw.len());
        latin1_decode(&raw[..cut])
    };
    let flags = u32::from_le_bytes(buf[pos + nbytes..pos + nbytes + 4].try_into().unwrap());
    Ok((text, flags, pos + nbytes + 4))
}
```

- [ ] **Step 4: Add tests for `read_name` (both name-table forms) and `read_fstring`**

Append inside the existing `#[cfg(test)] mod tests` block:

```rust
    #[test]
    fn read_name_v69_ansi_form() {
        // length=5 ("Hello"), no embedded NUL before the declared length, then 4 flag bytes.
        let mut buf = vec![0x05u8]; // compact index 5
        buf.extend_from_slice(b"Hello");
        buf.extend_from_slice(&0x04000000u32.to_le_bytes()); // RF_Native
        let (text, flags, next) = read_name(&buf, 0, 69).unwrap();
        assert_eq!(text, "Hello");
        assert_eq!(flags, 0x04000000);
        assert_eq!(next, buf.len());
    }

    #[test]
    fn read_name_v69_negative_length_is_utf16le() {
        // "Ab" in UTF-16LE = 4 bytes = 2 code units -> length is encoded as -2.
        let (neg2, _) = (-2i64, ());
        let mut buf = Vec::new();
        // compact index encoding of -2: single byte, bit7=sign, bits0-5=2 -> 0x82.
        buf.push(0x82u8);
        buf.extend_from_slice("Ab".encode_utf16().flat_map(|u| u.to_le_bytes()).collect::<Vec<u8>>().as_slice());
        buf.extend_from_slice(&0u32.to_le_bytes());
        let (text, flags, next) = read_name(&buf, 0, 69).unwrap();
        assert_eq!(text, "Ab");
        assert_eq!(flags, 0);
        assert_eq!(next, buf.len());
        let _ = neg2;
    }

    #[test]
    fn read_name_v61_null_terminated_form() {
        let mut buf = b"Engine".to_vec();
        buf.push(0);
        buf.extend_from_slice(&0x400u32.to_le_bytes()); // RF_HighlightName
        let (text, flags, next) = read_name(&buf, 0, 61).unwrap();
        assert_eq!(text, "Engine");
        assert_eq!(flags, 0x400);
        assert_eq!(next, buf.len());
    }

    #[test]
    fn read_fstring_matches_read_name_ansi_form_minus_flags() {
        let mut buf = vec![0x03u8];
        buf.extend_from_slice(b"Foo");
        let (text, next) = read_fstring(&buf, 0).unwrap();
        assert_eq!(text, "Foo");
        assert_eq!(next, buf.len());
    }
```

- [ ] **Step 5: Run all `package_read` tests, verify green**

Run: `cd uedcli-native && cargo test package_read -- --nocapture`
Expected: all 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add uedcli-native/src/package_read.rs uedcli-native/src/lib.rs
git commit -m "Add UE1 package byte-cursor primitives in Rust"
```

---

### Task 2: Rust header + name/import/export table walk

**Files:**
- Modify: `uedcli-native/src/package_read.rs` (append)

**Interfaces:**
- Consumes: `read_compact_index`, `read_name` from Task 1.
- Produces:
  ```rust
  pub struct ExportEntry {
      pub cls: i64, pub sup: i64, pub outer: i32, pub nm: i64,
      pub flags: u32, pub ssize: i64, pub soff: i64,
  }
  pub struct RawPackage {
      pub version: u16, pub licensee: u16, pub flags: u32,
      pub names: Vec<(String, u32)>,           // (text, per-entry flags)
      pub imports: Vec<(i64, i64, i32, i64)>,  // (ClassPackage, ClassName, PackageIndex, ObjectName)
      pub exports: Vec<ExportEntry>,
      pub name_offset: usize, pub name_count: usize,
      pub import_offset: usize, pub import_count: usize,
      pub export_offset: usize, pub export_count: usize,
      pub guid_range: Option<(usize, usize)>,
  }
  pub fn parse_package(buf: &[u8]) -> Result<RawPackage, BuildError>
  ```
  `parse_package` is what later tasks' PyO3 binding calls.

Faithful port of `upackage._parse_package` (line 201), with `utexture.py`'s DoS count-bound guard
(line ~145, ported below) applied universally, plus the raw offsets/`licensee`/`guid_range` fields
`gate.py`'s `_parse_header`/`Header` (`gate.py:28-49`) needs for PR2.

- [ ] **Step 1: Write `parse_package` with a hand-built synthetic-package test**

Append to `package_read.rs`:

```rust
const MAGIC: u32 = 0x9E2A83C1;
const HEADER_FIXED: usize = 36; // 9 little-endian u32: tag, version|licensee, flags, (count,offset)*3

#[derive(Debug, Clone)]
pub struct ExportEntry {
    pub cls: i64,
    pub sup: i64,
    pub outer: i32,
    pub nm: i64,
    pub flags: u32,
    pub ssize: i64,
    pub soff: i64,
}

#[derive(Debug, Clone)]
pub struct RawPackage {
    pub version: u16,
    pub licensee: u16,
    pub flags: u32,
    pub names: Vec<(String, u32)>,
    pub imports: Vec<(i64, i64, i32, i64)>,
    pub exports: Vec<ExportEntry>,
    pub name_offset: usize,
    pub name_count: usize,
    pub import_offset: usize,
    pub import_count: usize,
    pub export_offset: usize,
    pub export_count: usize,
    pub guid_range: Option<(usize, usize)>,
}

fn u32_at(buf: &[u8], pos: usize, what: &str) -> Result<u32, BuildError> {
    buf.get(pos..pos + 4)
        .map(|s| u32::from_le_bytes(s.try_into().unwrap()))
        .ok_or_else(|| BuildError(format!("{what}: buffer overrun at byte {pos}")))
}

fn i32_at(buf: &[u8], pos: usize, what: &str) -> Result<i32, BuildError> {
    Ok(u32_at(buf, pos, what)? as i32)
}

/// Header + name/import/export table walk. Faithful port of `upackage._parse_package`, with
/// `utexture.py`'s declared-count DoS guard applied universally (a header claiming a name/import/
/// export count larger than the file itself is refused before any entry is read — measured
/// upstream: an unguarded 0xFFFFFFFF count loops for 200s+ inside a 2.5GB cap without returning).
pub fn parse_package(buf: &[u8]) -> Result<RawPackage, BuildError> {
    if buf.len() < HEADER_FIXED {
        return Err(BuildError(format!(
            "too small to be an Unreal package ({} bytes)",
            buf.len()
        )));
    }
    let tag = u32_at(buf, 0, "header")?;
    if tag != MAGIC {
        return Err(BuildError(format!("bad magic {tag:#010x} (not an Unreal package)")));
    }
    let ver_l = u32_at(buf, 4, "header")?;
    let flags = u32_at(buf, 8, "header")?;
    let namecnt = u32_at(buf, 12, "header")? as usize;
    let nameoff = u32_at(buf, 16, "header")? as usize;
    let expcnt = u32_at(buf, 20, "header")? as usize;
    let expoff = u32_at(buf, 24, "header")? as usize;
    let impcnt = u32_at(buf, 28, "header")? as usize;
    let impoff = u32_at(buf, 32, "header")? as usize;

    let version = (ver_l & 0xFFFF) as u16;
    let licensee = (ver_l >> 16) as u16;
    let guid_range = if version >= 68 { Some((HEADER_FIXED, HEADER_FIXED + 16)) } else { None };

    for (what, count) in [("name", namecnt), ("import", impcnt), ("export", expcnt)] {
        if count > buf.len() {
            return Err(BuildError(format!(
                "header declares {count} {what} table entries in a {}-byte file",
                buf.len()
            )));
        }
    }

    let mut names = Vec::with_capacity(namecnt);
    let mut pos = nameoff;
    for _ in 0..namecnt {
        let (text, entry_flags, next) = read_name(buf, pos, version)?;
        names.push((text, entry_flags));
        pos = next;
    }

    let mut imports = Vec::with_capacity(impcnt);
    pos = impoff;
    for _ in 0..impcnt {
        let (cp, next) = read_compact_index(buf, pos)?;
        let (cn, next) = read_compact_index(buf, next)?;
        let pi = i32_at(buf, next, "import.PackageIndex")?;
        let (on, next) = read_compact_index(buf, next + 4)?;
        imports.push((cp, cn, pi, on));
        pos = next;
    }

    let mut exports = Vec::with_capacity(expcnt);
    pos = expoff;
    for _ in 0..expcnt {
        let (cls, next) = read_compact_index(buf, pos)?;
        let (sup, next) = read_compact_index(buf, next)?;
        let outer = i32_at(buf, next, "export.Outer")?;
        let (nm, next) = read_compact_index(buf, next + 4)?;
        let flv = u32_at(buf, next, "export.ObjectFlags")?;
        let (ssize, next) = read_compact_index(buf, next + 4)?;
        let (soff, next) = if ssize > 0 {
            read_compact_index(buf, next)?
        } else {
            (0, next)
        };
        exports.push(ExportEntry { cls, sup, outer, nm, flags: flv, ssize, soff });
        pos = next;
    }

    if pos > buf.len() {
        return Err(BuildError(format!(
            "export table overran EOF (cursor {pos} > size {}) — truncated or desynced package",
            buf.len()
        )));
    }

    Ok(RawPackage {
        version, licensee, flags, names, imports, exports,
        name_offset: nameoff, name_count: namecnt,
        import_offset: impoff, import_count: impcnt,
        export_offset: expoff, export_count: expcnt,
        guid_range,
    })
}

#[cfg(test)]
mod parse_tests {
    use super::*;

    /// Hand-builds the smallest valid v69 package: 1 name ("None"), 0 imports, 0 exports.
    fn synthetic_v69_empty() -> Vec<u8> {
        let mut names_blob = Vec::new();
        names_blob.push(0x04u8); // compact index 4 ("None".len())
        names_blob.extend_from_slice(b"None");
        names_blob.extend_from_slice(&0u32.to_le_bytes()); // flags

        let name_offset = HEADER_FIXED + 16; // header + GUID (v>=68)
        let mut buf = vec![0u8; name_offset];
        buf[0..4].copy_from_slice(&MAGIC.to_le_bytes());
        buf[4..8].copy_from_slice(&69u32.to_le_bytes()); // version=69, licensee=0
        buf[8..12].copy_from_slice(&0u32.to_le_bytes()); // flags
        buf[12..16].copy_from_slice(&1u32.to_le_bytes()); // namecnt
        buf[16..20].copy_from_slice(&(name_offset as u32).to_le_bytes()); // nameoff
        buf[20..24].copy_from_slice(&0u32.to_le_bytes()); // expcnt
        buf[24..28].copy_from_slice(&(name_offset as u32 + names_blob.len() as u32).to_le_bytes()); // expoff
        buf[28..32].copy_from_slice(&0u32.to_le_bytes()); // impcnt
        buf[32..36].copy_from_slice(&(name_offset as u32 + names_blob.len() as u32).to_le_bytes()); // impoff
        buf.extend_from_slice(&names_blob);
        buf
    }

    #[test]
    fn parses_synthetic_empty_v69_package() {
        let buf = synthetic_v69_empty();
        let pkg = parse_package(&buf).unwrap();
        assert_eq!(pkg.version, 69);
        assert_eq!(pkg.licensee, 0);
        assert_eq!(pkg.names, vec![("None".to_string(), 0u32)]);
        assert!(pkg.imports.is_empty());
        assert!(pkg.exports.is_empty());
        assert_eq!(pkg.guid_range, Some((36, 52)));
    }

    #[test]
    fn rejects_bad_magic() {
        let mut buf = synthetic_v69_empty();
        buf[0] = 0;
        let err = parse_package(&buf).unwrap_err();
        assert!(err.0.contains("bad magic"), "message: {}", err.0);
    }

    #[test]
    fn rejects_absurd_declared_count() {
        let mut buf = synthetic_v69_empty();
        buf[12..16].copy_from_slice(&0xFFFFFFFFu32.to_le_bytes()); // namecnt
        let err = parse_package(&buf).unwrap_err();
        assert!(err.0.contains("declares"), "message: {}", err.0);
    }

    #[test]
    fn v61_has_no_guid_range() {
        let mut buf = synthetic_v69_empty();
        buf[4..8].copy_from_slice(&61u32.to_le_bytes());
        let pkg = parse_package(&buf).unwrap();
        assert_eq!(pkg.guid_range, None);
    }
}
```

- [ ] **Step 2: Run the new tests, verify green**

Run: `cd uedcli-native && cargo test parse_tests -- --nocapture`
Expected: 4 tests pass.

- [ ] **Step 3: Commit**

```bash
git add uedcli-native/src/package_read.rs
git commit -m "Add Rust header/name/import/export table walk (parse_package)"
```

---

### Task 3: Rust tagged-property list decode

**Files:**
- Modify: `uedcli-native/src/package_read.rs` (append)

**Interfaces:**
- Consumes: `read_compact_index`, `read_array_index` from Task 1.
- Produces:
  ```rust
  pub struct RawPropertyTag {
      pub name: String, pub ptype: u8, pub struct_name: Option<String>,
      pub array_index: i64, pub bool_value: Option<bool>, pub raw: Vec<u8>,
      pub span: (usize, usize),
  }
  pub fn read_property_tags(buf: &[u8], pos: usize, end: usize, names: &[String])
      -> Result<(Vec<RawPropertyTag>, usize), BuildError>
  ```

Faithful port of `upackage.read_property_tags` (line 275). Takes `names: &[String]` (bare text
only — flags aren't needed here) so Rust resolves tag names itself, matching the Python function's
existing behavior of reading `pkg.names[nidx]` inline.

- [ ] **Step 1: Write `read_property_tags` with tests**

Append to `package_read.rs`:

```rust
const PT_BOOL: u8 = 3;
const PT_STRUCT: u8 = 10;

#[derive(Debug, Clone)]
pub struct RawPropertyTag {
    pub name: String,
    pub ptype: u8,
    pub struct_name: Option<String>,
    pub array_index: i64,
    pub bool_value: Option<bool>,
    pub raw: Vec<u8>,
    pub span: (usize, usize),
}

/// The UE1 tagged-property list: FName compact (name; "None" terminates) + info byte
/// [bits0-3 type | bits4-6 size code | bit7 array-flag/bool-value] + (StructProperty only)
/// struct-name compact + explicit size bytes per the size code + (non-bool, bit7 set) packed
/// array index + `size` raw value bytes. Faithful port of `upackage.read_property_tags`.
pub fn read_property_tags(
    buf: &[u8],
    pos: usize,
    end: usize,
    names: &[String],
) -> Result<(Vec<RawPropertyTag>, usize), BuildError> {
    if end > buf.len() {
        return Err(BuildError(format!(
            "tagged-property list bounds exceed the file ({end} > {})",
            buf.len()
        )));
    }
    let mut pos = pos;
    let mut tags = Vec::new();
    loop {
        if pos >= end {
            return Err(BuildError(format!(
                "tagged-property list overran its bounds at {pos} (no None)"
            )));
        }
        let tag_start = pos;
        let (nidx, next) = read_compact_index(buf, pos)?;
        pos = next;
        let name = names
            .get(usize::try_from(nidx).unwrap_or(usize::MAX))
            .cloned()
            .filter(|_| nidx >= 0)
            .ok_or_else(|| BuildError(format!("tagged-property name index {nidx} out of range at {pos}")))?;
        if name == "None" {
            return Ok((tags, pos));
        }
        let info = *buf.get(pos).ok_or_else(|| BuildError(format!("property tag info byte overrun at {pos}")))?;
        pos += 1;
        let ptype = info & 0x0F;
        let size_code = (info >> 4) & 0x07;
        let bit7 = info & 0x80 != 0;
        let mut struct_name = None;
        if ptype == PT_STRUCT {
            let (sidx, next) = read_compact_index(buf, pos)?;
            pos = next;
            struct_name = names.get(usize::try_from(sidx).unwrap_or(usize::MAX)).filter(|_| sidx >= 0).cloned();
        }
        let size: u32 = match size_code {
            0 => 1, 1 => 2, 2 => 4, 3 => 12, 4 => 16,
            5 => { let s = *buf.get(pos).ok_or_else(|| BuildError(format!("size byte overrun at {pos}")))?; pos += 1; s as u32 }
            6 => { let s = u16_at(buf, pos)?; pos += 2; s as u32 }
            _ => { let s = u32_at(buf, pos, "property size")?; pos += 4; s }
        };
        if ptype == PT_BOOL {
            tags.push(RawPropertyTag {
                name, ptype, struct_name: None, array_index: 0,
                bool_value: Some(bit7), raw: Vec::new(), span: (tag_start, pos),
            });
            continue;
        }
        let mut array_index = 0i64;
        if bit7 {
            let (ai, next) = read_array_index(buf, pos)?;
            array_index = ai;
            pos = next;
        }
        if pos + size as usize > end {
            return Err(BuildError(format!(
                "tagged property {name} value overruns its bounds ({pos}+{size} > {end})"
            )));
        }
        let raw = buf[pos..pos + size as usize].to_vec();
        pos += size as usize;
        tags.push(RawPropertyTag {
            name, ptype, struct_name, array_index,
            bool_value: None, raw, span: (tag_start, pos),
        });
    }
}

fn u16_at(buf: &[u8], pos: usize) -> Result<u16, BuildError> {
    buf.get(pos..pos + 2)
        .map(|s| u16::from_le_bytes(s.try_into().unwrap()))
        .ok_or_else(|| BuildError(format!("u16 read: buffer overrun at byte {pos}")))
}

#[cfg(test)]
mod property_tag_tests {
    use super::*;

    #[test]
    fn reads_a_bool_tag_then_none() {
        let names = vec!["bDeleteMe".to_string(), "None".to_string()];
        // Tag 1: name idx 0, info byte = ptype 3 (bool) | bit7 set (true value).
        let mut buf = vec![0x00u8, 0x83u8];
        // Terminator: name idx 1 ("None").
        buf.push(0x01);
        let (tags, pos) = read_property_tags(&buf, 0, buf.len(), &names).unwrap();
        assert_eq!(tags.len(), 1);
        assert_eq!(tags[0].name, "bDeleteMe");
        assert_eq!(tags[0].bool_value, Some(true));
        assert_eq!(pos, buf.len());
    }

    #[test]
    fn missing_none_terminator_is_an_error() {
        let names = vec!["x".to_string()];
        let buf = vec![0x00u8, 0x02u8, 0xAA, 0xBB]; // an int tag (ptype 2, size_code 0->1 byte... truncated on purpose
        let err = read_property_tags(&buf, 0, buf.len(), &names);
        assert!(err.is_err());
    }
}
```

- [ ] **Step 2: Run tests, verify green**

Run: `cd uedcli-native && cargo test property_tag_tests -- --nocapture`
Expected: 2 tests pass.

- [ ] **Step 3: Run the FULL `package_read` test module (all tasks so far) once more**

Run: `cd uedcli-native && cargo test package_read`
Expected: every test added in Tasks 1-3 passes (13 tests total).

- [ ] **Step 4: Commit**

```bash
git add uedcli-native/src/package_read.rs
git commit -m "Add Rust tagged-property list decode (read_property_tags)"
```

---

### Task 4: PyO3 bindings

**Files:**
- Modify: `uedcli-native/src/lib.rs`

**Interfaces:**
- Consumes: `package_read::{parse_package, read_property_tags, RawPackage, ExportEntry, RawPropertyTag}`.
- Produces (the Python-visible surface):
  - `uedcli_native.PackageError` (new exception class)
  - `uedcli_native.parse_package_raw(buf: bytes) -> tuple` — see the exact tuple shape in Step 1.
  - `uedcli_native.read_property_tags_raw(buf: bytes, pos: int, end: int, names: list[str]) -> tuple[list[tuple], int]`

- [ ] **Step 1: Add the `mod` declaration, the exception, and `parse_package_raw`**

In `uedcli-native/src/lib.rs`, near the existing `create_exception!` calls (find
`create_exception!(uedcli_native, PathError, ...)`), add:

```rust
create_exception!(uedcli_native, PackageError, pyo3::exceptions::PyException);

fn map_pkg_err(e: model::BuildError) -> PyErr {
    PackageError::new_err(e.to_string())
}
```

**Type path note (pre-flight-checked, not a typo to "fix" the other way):** `package_read.rs`
reuses `crate::model::BuildError` as its OWN error type (Task 1 already specified this — it does
NOT define its own error type). The parameter here must be `model::BuildError` (whatever path
alias `lib.rs` already uses for that module — check the existing `map_err`'s signature and copy
its exact type path), never `package_read::BuildError`, which doesn't exist. Use `.to_string()`
the way the existing `map_err` does — do not assume the field is public.

Near the top with the other `mod` declarations, add: `mod package_read;`

Then add the binding function (place it near `serialize_model`, since it's a similarly-shaped
"parse/serialize primitive" rather than a build/lighting one):

```rust
type RawPackageOut = (
    u16,                     // version
    u16,                     // licensee
    u32,                     // flags
    Vec<(String, u32)>,      // names: (text, entry_flags)
    Vec<(i64, i64, i32, i64)>, // imports: (ClassPackage, ClassName, PackageIndex, ObjectName)
    Vec<(i64, i64, i32, i64, u32, i64, i64)>, // exports: (cls, sup, outer, nm, flags, ssize, soff)
    usize, usize,            // name_offset, name_count
    usize, usize,            // import_offset, import_count
    usize, usize,            // export_offset, export_count
    Option<(usize, usize)>,  // guid_range
);

#[pyfunction]
fn parse_package_raw(py: Python<'_>, buf: Vec<u8>) -> PyResult<RawPackageOut> {
    let pkg = py
        .allow_threads(|| package_read::parse_package(&buf))
        .map_err(map_pkg_err)?;
    Ok((
        pkg.version, pkg.licensee, pkg.flags, pkg.names, pkg.imports,
        pkg.exports.into_iter().map(|e| (e.cls, e.sup, e.outer, e.nm, e.flags, e.ssize, e.soff)).collect(),
        pkg.name_offset, pkg.name_count,
        pkg.import_offset, pkg.import_count,
        pkg.export_offset, pkg.export_count,
        pkg.guid_range,
    ))
}

type RawPropertyTagOut = (String, u8, Option<String>, i64, Option<bool>, Vec<u8>, (usize, usize));

#[pyfunction]
fn read_property_tags_raw(
    py: Python<'_>, buf: Vec<u8>, pos: usize, end: usize, names: Vec<String>,
) -> PyResult<(Vec<RawPropertyTagOut>, usize)> {
    let (tags, next) = py
        .allow_threads(|| package_read::read_property_tags(&buf, pos, end, &names))
        .map_err(map_pkg_err)?;
    Ok((
        tags.into_iter()
            .map(|t| (t.name, t.ptype, t.struct_name, t.array_index, t.bool_value, t.raw, t.span))
            .collect(),
        next,
    ))
}
```

- [ ] **Step 2: Register both functions + the exception in `#[pymodule]`**

In `uedcli-native/src/lib.rs`'s `#[pymodule] fn uedcli_native(...)` block, add near the other
`m.add`/`m.add_function` lines:

```rust
    m.add("PackageError", m.py().get_type_bound::<PackageError>())?;
    m.add_function(wrap_pyfunction!(parse_package_raw, m)?)?;
    m.add_function(wrap_pyfunction!(read_property_tags_raw, m)?)?;
```

- [ ] **Step 3: Build and run `cargo test` for the whole crate**

Run: use whatever `bin/_venv.sh` invokes for `cargo test` (check the exact command in
`bin/_venv.sh` first — do not assume `cd uedcli-native && cargo test` matches its Docker/uid
setup exactly; match it).
Expected: all existing crate tests plus the 13 new ones from Tasks 1-3 pass. No warnings about
unused `map_pkg_err`/functions (both are now called).

- [ ] **Step 4: Rebuild the Python extension**

Run: whatever `bin/_venv.sh` does for `maturin build --release` (check the exact invocation first).
Expected: a fresh wheel; `import uedcli_native; uedcli_native.parse_package_raw` is now callable
from Python. Sanity-check in a Python shell:

```python
import uedcli_native
uedcli_native.parse_package_raw(b"not a package")
```
Expected: raises `uedcli_native.PackageError`, not a bare exception or a crash.

- [ ] **Step 5: Commit**

```bash
git add uedcli-native/src/lib.rs
git commit -m "Expose parse_package_raw/read_property_tags_raw via PyO3"
```

---

### Task 5: Rewire `upackage.py` onto the Rust core

**Files:**
- Modify: `uedcli/upackage.py`
- Create: `uedcli/tests/test_upackage.py`

**Interfaces:**
- Consumes: `uedcli_native.parse_package_raw`, `uedcli_native.read_property_tags_raw`,
  `uedcli_native.PackageError` (Task 4).
- Produces: `Package` gains `name_entries: list[NameEntry]`, `licensee: int`, `name_offset: int`,
  `name_count: int`, `import_offset: int`, `import_count: int`, `export_offset: int`,
  `export_count: int`, `guid_range: tuple[int, int] | None`. New `NameEntry` frozen dataclass
  (`text: str`, `flags: int`). Every OTHER existing field/method/function keeps its exact name and
  signature — this is the frozen public API from the plan header.

- [ ] **Step 1: Write the failing test for the new fields**

Create `uedcli/tests/test_upackage.py`:

```python
"""Unit tests for upackage.py's Rust-backed core. Broader coverage (real files, every existing
caller) lives in test_dxpkg.py/test_utexture_corpus.py/test_native_roundtrip.py/uscript's own
suites — this file covers upackage.py's own new surface directly."""
import struct

import pytest

from uedcli.upackage import (MAGIC, NameEntry, Package, SchemaError, load_package,
                             parse_package_bytes, read_compact_index, read_fstring)


def _synthetic_v69_empty() -> bytes:
    """The smallest valid v69 package: one name ("None"), no imports, no exports."""
    names_blob = bytes([0x04]) + b"None" + struct.pack("<I", 0)
    header_fixed = 36
    name_offset = header_fixed + 16  # header + GUID
    buf = bytearray(name_offset)
    struct.pack_into("<9I", buf, 0,
                      MAGIC, 69, 0, 1, name_offset, 0,
                      name_offset + len(names_blob), 0, name_offset + len(names_blob))
    buf += names_blob
    return bytes(buf)


def test_parses_synthetic_package_and_keeps_names_as_bare_strings():
    pkg = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")
    assert pkg.names == ["None"]
    assert pkg.version == 69
    assert pkg.licensee == 0


def test_name_entries_carries_flags_alongside_names():
    pkg = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")
    assert pkg.name_entries == [NameEntry(text="None", flags=0)]
    assert len(pkg.name_entries) == len(pkg.names)


def test_guid_range_present_for_v68_plus_absent_below():
    pkg = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")
    assert pkg.guid_range == (36, 52)


def test_table_offsets_exposed():
    pkg = parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")
    assert pkg.name_offset == 52
    assert pkg.name_count == 1
    assert pkg.import_count == 0
    assert pkg.export_count == 0


def test_bad_magic_raises_schema_error():
    with pytest.raises(SchemaError):
        parse_package_bytes(b"not a package" + b"\x00" * 40, where="<test>")


def test_absurd_declared_count_raises_schema_error():
    buf = bytearray(_synthetic_v69_empty())
    struct.pack_into("<I", buf, 12, 0xFFFFFFFF)  # namecnt
    with pytest.raises(SchemaError):
        parse_package_bytes(bytes(buf), where="<test>")


def test_read_compact_index_still_works_standalone():
    assert read_compact_index(bytes([0x05]), 0) == (5, 1)
    assert read_compact_index(bytes([0x85]), 0) == (-5, 1)


def test_read_fstring_still_works_standalone():
    assert read_fstring(bytes([0x03]) + b"Foo", 0) == ("Foo", 4)


def test_dx_unicode_group_name_decodes(tmp_path):
    """The negative-length UTF-16LE branch upackage.py previously lacked (only dxpkg.py had it)."""
    import pathlib
    fixture = pathlib.Path("/workspace/dx_lum/Maps/20_AireGardens.dx")
    if not fixture.exists():
        pytest.skip("real DX Unicode-name fixture not present on this host")
    pkg = load_package(str(fixture))
    assert any("\x00" not in n for n in pkg.names)  # sanity: names decoded, not raw garbage
```

- [ ] **Step 2: Run the test file, verify it FAILS (Rust wiring doesn't exist yet)**

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_upackage.py -v`
Expected: `ImportError`/`AttributeError` on `NameEntry` (doesn't exist yet in `upackage.py`), or
similar — the point is it fails for the RIGHT reason (missing new surface), not a typo.

- [ ] **Step 3: Rewrite `upackage.py`'s parsing internals to call Rust**

In `uedcli/upackage.py`:

1. Add the import near the top (after the existing imports):
   ```python
   import uedcli_native
   ```

2. Add the `NameEntry` dataclass right after `SchemaError`'s definition (around line 38):
   ```python
   @dataclass(frozen=True, kw_only=True)
   class NameEntry:
       """One name-table row as the wire format actually stores it: text plus the real engine's
       per-entry EObjectFlags bits (RF_Native = 0x04000000, RF_HighlightName = 0x400 — see
       USCRIPT-COMPILER.md). Named for the concept, not the engine's own `FNameEntry` struct: this
       module already drops Epic's struct-prefix convention (`Package`, `PropertyTag`), and the
       real `FNameEntry` also carries a runtime-only hash/next-pointer this never touches."""
       text: str
       flags: int
   ```

3. Extend the `Package` dataclass (around line 79) with the new fields — add them AFTER the
   existing `buf: bytes` field (frozen dataclasses with `kw_only=True` don't care about field
   order for defaults, but keep the diff minimal by appending):
   ```python
   @dataclass(frozen=True, kw_only=True)
   class Package:
       name: str
       version: int
       names: list[str]
       imports: list[tuple[int, int, int, int]]
       exports: list[dict]
       buf: bytes
       name_entries: list[NameEntry]
       licensee: int
       name_offset: int
       name_count: int
       import_offset: int
       import_count: int
       export_offset: int
       export_count: int
       guid_range: tuple[int, int] | None
       # ... (name_of_ref, import_package_of, object_path, object_class_name UNCHANGED — do not
       # touch their bodies, they operate on .names/.exports/.imports exactly as before)
   ```

4. Replace `_parse_package`'s body (lines 201-247) — keep the function name and signature
   identical, delete the hand-rolled loop, call Rust instead:

   **Interface correction from Task 4 (already built, verify against the actual code, not this
   text): `parse_package_raw`'s return tuple is NOT flat.** PyO3 0.22's tuple `IntoPy` caps at 12
   elements; the brief's original flat 13-tuple didn't compile. Task 4 nested the three
   `(offset, count)` pairs into sub-tuples, bringing top-level arity to 10:
   ```rust
   type RawPackageOut = (
       u16, u16, u32,                              // version, licensee, flags
       Vec<(String, u32)>,                          // names
       Vec<(i64, i64, i32, i64)>,                   // imports
       Vec<(i64, i64, i32, i64, u32, i64, i64)>,    // exports
       (usize, usize),                              // (name_offset, name_count)
       (usize, usize),                              // (import_offset, import_count)
       (usize, usize),                              // (export_offset, export_count)
       Option<(usize, usize)>,                      // guid_range
   );
   ```
   Destructure accordingly:
   ```python
   def _parse_package(buf: bytes, path: str, name: str | None) -> Package:
       try:
           (version, licensee, flags, names_with_flags, imports, exports_raw,
            (name_offset, name_count), (import_offset, import_count),
            (export_offset, export_count), guid_range) = uedcli_native.parse_package_raw(buf)
       except uedcli_native.PackageError as e:
           raise SchemaError(f"{path}: {e}") from e
       names = [text for text, _flags in names_with_flags]
       name_entries = [NameEntry(text=text, flags=flags_) for text, flags_ in names_with_flags]
       exports = [
           dict(cls=cls, sup=sup, outer=outer, nm=nm, flags=flv, ssize=ssize, soff=soff)
           for cls, sup, outer, nm, flv, ssize, soff in exports_raw
       ]
       return Package(
           name=name or os.path.splitext(os.path.basename(path))[0], version=version,
           names=names, imports=imports, exports=exports, buf=buf,
           name_entries=name_entries, licensee=licensee,
           name_offset=name_offset, name_count=name_count,
           import_offset=import_offset, import_count=import_count,
           export_offset=export_offset, export_count=export_count,
           guid_range=guid_range,
       )
   ```
   Keep `parse_package_bytes` and `load_package` completely unchanged (they already just delegate
   to `_parse_package`) — their `SchemaError` wrapping (catching `struct.error`/`ValueError`/
   `IndexError`) becomes dead code for the Rust path but stays as-is for now (harmless, and
   `parse_package_bytes`'s own `len(buf) < 36` pre-check is still real Python that runs first).

5. Replace `read_property_tags`'s body (lines 275-322) — keep the function name/signature
   identical:
   ```python
   def read_property_tags(pkg: Package, pos: int, end: int) -> tuple[list[PropertyTag], int]:
       try:
           raw_tags, next_pos = uedcli_native.read_property_tags_raw(pkg.buf, pos, end, pkg.names)
       except uedcli_native.PackageError as e:
           raise SchemaError(str(e)) from e
       tags = [
           PropertyTag(name=name, ptype=ptype, struct_name=struct_name, array_index=array_index,
                       bool_value=bool_value, raw=bytes(raw), span=span)
           for name, ptype, struct_name, array_index, bool_value, raw, span in raw_tags
       ]
       return tags, next_pos
   ```
   Delete the now-dead `PT_*`/`_SIZE_FIXED` constants' USE inside the old loop body — but KEEP the
   constants themselves (`PT_BYTE` through `PT_FIXED`, `_SIZE_FIXED`) since other modules
   (`utexture.py`, `uprops/*`) import `ptype` values to compare against them.

6. Delete `read_array_index`'s Python body? **No** — keep it. `read_compact_index`,
   `read_fstring`, `read_array_index` stay as pure-Python public functions (frozen API, several
   test files and `gate.py`/`reorder.py` call them directly) — they are simply no longer called by
   `_parse_package`/`read_property_tags` internally, but remain correct, tested, standalone
   utilities. Do not delete them.

- [ ] **Step 4: Run the new test file, verify it passes**

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_upackage.py -v`
Expected: all tests pass (the DX-Unicode test skips if the fixture isn't present on this host).

- [ ] **Step 5: Run the broader existing suites that exercise `upackage.py` transitively**

Run:
```bash
TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s \
  uedcli/tests/test_dxpkg.py uedcli/tests/test_utexture_corpus.py uedcli/tests/test_utexture_blocks.py \
  uedcli/tests/test_mapimport_import.py uedcli/tests/test_mapimport_array.py \
  uedcli/tests/test_mesh_decode.py uedcli/tests/test_native_roundtrip.py \
  uedcli/tests/test_v61_model_decode.py uedcli/tests/test_uscript_bytecode.py \
  uedcli/tests/test_module_layering.py -v
```
Expected: all pass, same skip pattern as before (real-fixture-gated tests skip identically to
pre-change behavior — nothing newly skips or newly fails).

- [ ] **Step 6: Commit**

```bash
git add uedcli/upackage.py uedcli/tests/test_upackage.py
git commit -m "Rewire upackage.py's table walk onto the Rust core"
```

---

### Task 6: In-process memoization in `load_package`

**Files:**
- Modify: `uedcli/upackage.py`
- Modify: `uedcli/tests/test_upackage.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `load_package` behavior unchanged from the caller's view — same signature, same
  return value — but a second call with the same resolved path within one process returns the
  cached `Package` instead of re-reading/re-parsing the file.

This directly fixes the mechanism found during planning: `preview_native.py`'s
`resolve_class_defaults(actor.cls, resolver=...)` call (no `_pkgs` passed) starts a fresh
package-loading walk per actor instance — 1439 times for `IsvKran32.unr`'s 108 distinct packages.
Memoizing `load_package` itself fixes this with no change to `preview_native.py`/`uprops/values.py`.

- [ ] **Step 1: Write the failing test**

Append to `uedcli/tests/test_upackage.py`:

```python
def test_load_package_memoizes_within_a_process(tmp_path, monkeypatch):
    pkg_path = tmp_path / "Test.u"
    pkg_path.write_bytes(_synthetic_v69_empty())

    calls = []
    real_parse = uedcli.upackage.parse_package_bytes

    def counting_parse(buf, **kw):
        calls.append(1)
        return real_parse(buf, **kw)

    import uedcli.upackage
    monkeypatch.setattr(uedcli.upackage, "parse_package_bytes", counting_parse)

    first = uedcli.upackage.load_package(str(pkg_path))
    second = uedcli.upackage.load_package(str(pkg_path))
    assert first is second  # same cached object, not just equal
    assert len(calls) == 1


def test_load_package_cache_invalidates_on_mtime_change(tmp_path):
    import os

    pkg_path = tmp_path / "Test.u"
    pkg_path.write_bytes(_synthetic_v69_empty())
    first = uedcli.upackage.load_package(str(pkg_path))

    st = os.stat(pkg_path)
    # Bump mtime_ns deterministically (no sleep-and-hope) to a value the cache hasn't seen,
    # keeping size identical -- proves invalidation keys on mtime_ns, not just size.
    os.utime(pkg_path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    second = uedcli.upackage.load_package(str(pkg_path))
    assert first is not second
```

Add `import uedcli.upackage` near the top of the test file's imports (alongside the existing
`from uedcli.upackage import ...`), since these two tests need the module object itself for
`monkeypatch.setattr`.

- [ ] **Step 2: Run the tests, verify they FAIL** (no memoization exists yet — `first is second`
  fails, `calls` has 2 entries)

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_upackage.py -k memoiz -v`

- [ ] **Step 3: Implement the in-process cache**

In `uedcli/upackage.py`, replace `load_package` (lines 177-186):

```python
_LOAD_CACHE: dict[str, tuple[int, int, "Package"]] = {}  # realpath -> (size, mtime_ns, Package)


def load_package(path: str, *, name: str | None = None) -> Package:
    """Parse a package header + name/import/export tables. Any malformed/truncated input raises
    `SchemaError` (bad magic, a too-short header, a byte-parse overrun, or an export table that
    does not consume to EOF) — the no-fallback integrity gate, so a corrupt package never reaches
    a caller as a bare `struct.error`/`IndexError` traceback.

    Memoized in-process by (realpath, size, mtime_ns): the same package is loaded repeatedly
    within one render (e.g. one actor class's package loaded once per actor instance sharing that
    class) — profiled at 3,404 calls for 108 distinct packages rendering one photo."""
    realpath = os.path.realpath(path)
    try:
        st = os.stat(realpath)
    except OSError as e:
        raise SchemaError(f"{path}: cannot read package ({e})") from e
    cached = _LOAD_CACHE.get(realpath)
    if cached is not None and cached[0] == st.st_size and cached[1] == st.st_mtime_ns:
        return cached[2]
    try:
        buf = open(realpath, "rb").read()
    except OSError as e:
        raise SchemaError(f"{path}: cannot read package ({e})") from e
    pkg = parse_package_bytes(buf, where=path, name=name)
    _LOAD_CACHE[realpath] = (st.st_size, st.st_mtime_ns, pkg)
    return pkg
```

- [ ] **Step 4: Run the tests, verify they pass**

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_upackage.py -k memoiz -v`
Expected: both pass.

- [ ] **Step 5: Run the full `test_upackage.py` file again (regression check on Task 5's tests)**

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_upackage.py -v`
Expected: all pass — the `name=` override behavior (loading the same path under two different
`name=` args) is NOT part of the cache key; if any existing caller relies on `load_package(path,
name=X)` then `load_package(path, name=Y)` returning different `Package.name` values for the same
path, this cache would break it. **Check for this before finalizing**: grep `load_package(` call
sites for any that pass differing `name=` for the same path across calls (unlikely — `name` is
almost always derived from the path itself) — if found, key the cache on `(realpath, name)` too,
not just `realpath`.

- [ ] **Step 6: Commit**

```bash
git add uedcli/upackage.py uedcli/tests/test_upackage.py
git commit -m "Memoize load_package in-process (fixes the 3,404-call/render pattern)"
```

---

### Task 7: On-disk cache tier

**Files:**
- Create: `uedcli/pkg_cache.py`
- Modify: `uedcli/config.py`
- Modify: `uedcli/upackage.py`
- Create: `uedcli/tests/test_pkg_cache.py`

**Interfaces:**
- Consumes: `uedcli.config.user_cache_home()`, `uedcli.stub_cache._atomic_write` (the existing
  atomic-write helper `schema_cache.py` already reuses — check its exact import path in
  `schema_cache.py` first and match it).
- Produces: `uedcli.config.pkg_cache_root(*, create: bool = False) -> Path`,
  `uedcli.pkg_cache.CacheWriteError`, `uedcli.pkg_cache.read(realpath, size, mtime_ns) -> Package | None`,
  `uedcli.pkg_cache.write(realpath, size, mtime_ns, pkg: Package) -> None`.

This is a SECOND tier below Task 6's in-process dict: it survives across separate CLI invocations
(cold processes), mirroring `schema_cache.py`'s exact proven scheme rather than inventing a new
one — read `uedcli/schema_cache.py` in full before writing this task's code, and match its key
derivation (a hash digest of `f"{VERSION}\0{realpath}\0{size}\0{mtime_ns}"`, NOT the raw tuple as a
literal path component), its `marshal` serialization, and its `_atomic_write`/`CacheWriteError`/
env-var-off-switch/`sweep()` pattern precisely.

- [ ] **Step 1: Read `schema_cache.py` in full** (no code yet) to confirm the exact functions this
  task must mirror: the cache-key hash function, `_write_blob`/`_read_blob`, `CacheWriteError`'s
  exact message shape (it must name `config.user_cache_home()` per `direction/packages.md`'s "a
  cache that cannot be written is a loud, actionable error naming the directory"), the
  `UEDCLI_SCHEMA_CACHE=off`-style env escape hatch (name this one `UEDCLI_PKG_CACHE`), and how
  `sweep()`/`uedcli cache gc` currently enumerates cache subdirectories (this new `pkg/` dir must
  be picked up by the SAME `cache gc` command, not a second one — check how `cache gc` currently
  discovers `schema/` and extend it, don't duplicate the CLI command).

- [ ] **Step 2: Add `pkg_cache_root()` to `config.py`**

In `uedcli/config.py`, next to `schema_cache_root()`:
```python
def pkg_cache_root(*, create: bool = False) -> Path:
    root = user_cache_home() / "pkg"
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root
```

- [ ] **Step 3: Write the failing test**

Create `uedcli/tests/test_pkg_cache.py` (structure mirrors whatever `test_schema_cache.py` does —
**read that file first if it exists**, to match its fixture/monkeypatch pattern for isolating
`UEDCLI_HOME` per test, rather than inventing a different isolation approach):

```python
"""Tests for the on-disk package-primitive cache (pkg_cache.py) — the second tier below
load_package's in-process memoization, surviving across separate CLI invocations."""
import os

import pytest

from uedcli import pkg_cache
from uedcli.upackage import parse_package_bytes


def _synthetic_pkg():
    from uedcli.tests.test_upackage import _synthetic_v69_empty
    return parse_package_bytes(_synthetic_v69_empty(), where="<test>", name="Test")


def test_write_then_read_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", 123, 456, pkg)
    back = pkg_cache.read("/fake/Test.u", 123, 456)
    assert back is not None
    assert back.names == pkg.names
    assert back.name_entries == pkg.name_entries


def test_stat_mismatch_is_a_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", 123, 456, pkg)
    assert pkg_cache.read("/fake/Test.u", 123, 999) is None  # different mtime_ns


def test_disabled_via_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path))
    monkeypatch.setenv("UEDCLI_PKG_CACHE", "off")
    pkg = _synthetic_pkg()
    pkg_cache.write("/fake/Test.u", 123, 456, pkg)
    assert pkg_cache.read("/fake/Test.u", 123, 456) is None


def test_write_failure_raises_loud_error(tmp_path, monkeypatch):
    monkeypatch.setenv("UEDCLI_HOME", str(tmp_path / "readonly"))
    (tmp_path / "readonly").mkdir()
    (tmp_path / "readonly").chmod(0o500)  # no write permission
    pkg = _synthetic_pkg()
    with pytest.raises(pkg_cache.CacheWriteError):
        pkg_cache.write("/fake/Test.u", 123, 456, pkg)
    (tmp_path / "readonly").chmod(0o700)  # restore so pytest can clean up tmp_path
```

- [ ] **Step 4: Run, verify FAILS** (module doesn't exist)

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_pkg_cache.py -v`

- [ ] **Step 5: Implement `uedcli/pkg_cache.py`**, mirroring `schema_cache.py`'s exact mechanism
  (key hash, `marshal`, atomic write, env-var off-switch, `CacheWriteError` naming the directory).
  The `Package`/`NameEntry` dataclasses need a marshal-able representation — `marshal` handles
  plain dicts/lists/tuples/str/int/bytes natively but NOT dataclass instances directly, so
  serialize/deserialize through plain dicts:

```python
"""On-disk cache for decoded package primitives (name/import/export tables) — the second tier
below upackage.load_package's in-process memoization. Mirrors schema_cache.py's exact scheme:
same stat-tuple-hash key, marshal serialization, atomic write, loud write-failure error.

`direction/packages.md`: "decoded package primitives are cached per-package on disk... A cache
that cannot be written is a loud, actionable error naming the directory."
"""
from __future__ import annotations

import hashlib
import marshal
import os

from . import config
from .upackage import NameEntry, Package

CACHE_VERSION = 1


class CacheWriteError(Exception):
    """The on-disk package cache directory could not be written. Never swallowed — a silently
    dead cache re-decodes every package on every run, invisibly."""


def _enabled() -> bool:
    return os.environ.get("UEDCLI_PKG_CACHE", "").strip().lower() != "off"


def _cache_key(realpath: str, size: int, mtime_ns: int) -> str:
    digest = hashlib.sha1(f"{CACHE_VERSION}\0{realpath}\0{size}\0{mtime_ns}".encode()).hexdigest()
    return digest


def _blob_path(realpath: str, size: int, mtime_ns: int) -> "os.PathLike[str]":
    key = _cache_key(realpath, size, mtime_ns)
    return config.pkg_cache_root() / f"v{CACHE_VERSION}" / f"{key}.pkg"


def _to_blob(pkg: Package) -> dict:
    return dict(
        name=pkg.name, version=pkg.version, names=pkg.names, imports=pkg.imports,
        exports=pkg.exports, buf=pkg.buf,
        name_entries=[(e.text, e.flags) for e in pkg.name_entries],
        licensee=pkg.licensee, name_offset=pkg.name_offset, name_count=pkg.name_count,
        import_offset=pkg.import_offset, import_count=pkg.import_count,
        export_offset=pkg.export_offset, export_count=pkg.export_count,
        guid_range=pkg.guid_range,
    )


def _from_blob(d: dict) -> Package:
    return Package(
        name=d["name"], version=d["version"], names=d["names"], imports=d["imports"],
        exports=d["exports"], buf=d["buf"],
        name_entries=[NameEntry(text=t, flags=f) for t, f in d["name_entries"]],
        licensee=d["licensee"], name_offset=d["name_offset"], name_count=d["name_count"],
        import_offset=d["import_offset"], import_count=d["import_count"],
        export_offset=d["export_offset"], export_count=d["export_count"],
        guid_range=d["guid_range"],
    )


def read(realpath: str, size: int, mtime_ns: int) -> Package | None:
    if not _enabled():
        return None
    path = _blob_path(realpath, size, mtime_ns)
    try:
        with open(path, "rb") as f:
            blob = marshal.load(f)
    except (OSError, ValueError, EOFError, TypeError):
        return None
    try:
        return _from_blob(blob)
    except (KeyError, TypeError):
        return None  # a version/shape mismatch is a silent miss, not a crash


def write(realpath: str, size: int, mtime_ns: int, pkg: Package) -> None:
    if not _enabled():
        return
    path = _blob_path(realpath, size, mtime_ns)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as f:
            marshal.dump(_to_blob(pkg), f)
        os.replace(tmp, path)
    except OSError as e:
        raise CacheWriteError(
            f"cannot write package cache under {config.user_cache_home()}: {e}"
        ) from e
```

(**Check `schema_cache.py`'s `_atomic_write` helper before finalizing this** — if it's a shared,
importable function (e.g. from `stub_cache.py`), call THAT instead of reimplementing tmp+replace
here, per the "no use-case reimplements" spirit. Same for whatever `sweep()`/`cache gc` hookup
`schema_cache.py` uses — wire `pkg/` into it rather than leaving it unswept.)

- [ ] **Step 6: Wire it into `load_package`**

In `uedcli/upackage.py`'s `load_package`, between the in-process cache miss and the file read, add
the on-disk tier. **Keep Task 6's docstring** — the code block below omits it only for brevity;
replace the function BODY, not the whole definition including its docstring:

```python
def load_package(path: str, *, name: str | None = None) -> Package:
    """(keep Task 6's existing docstring here verbatim, then extend its final sentence to
    mention the on-disk tier: "...profiled at 3,404 calls for 108 distinct packages rendering
    one photo. A second, on-disk tier (pkg_cache.py) survives across separate CLI invocations.")"""
    realpath = os.path.realpath(path)
    try:
        st = os.stat(realpath)
    except OSError as e:
        raise SchemaError(f"{path}: cannot read package ({e})") from e
    cached = _LOAD_CACHE.get(realpath)
    if cached is not None and cached[0] == st.st_size and cached[1] == st.st_mtime_ns:
        return cached[2]
    from . import pkg_cache  # local import: pkg_cache imports Package/NameEntry from here
    disk_hit = pkg_cache.read(realpath, st.st_size, st.st_mtime_ns)
    if disk_hit is not None:
        _LOAD_CACHE[realpath] = (st.st_size, st.st_mtime_ns, disk_hit)
        return disk_hit
    try:
        buf = open(realpath, "rb").read()
    except OSError as e:
        raise SchemaError(f"{path}: cannot read package ({e})") from e
    pkg = parse_package_bytes(buf, where=path, name=name)
    _LOAD_CACHE[realpath] = (st.st_size, st.st_mtime_ns, pkg)
    pkg_cache.write(realpath, st.st_size, st.st_mtime_ns, pkg)
    return pkg
```

(The `from . import pkg_cache` is a local import specifically to break the circular import —
`pkg_cache.py` imports `Package`/`NameEntry` from `upackage.py`, so `upackage.py` cannot import
`pkg_cache` at module level. Per `CLAUDE.md`'s import rule, a local import is allowed for
circularity — this is exactly that case.)

**Pre-flight-checked cross-task fix, do this in the same step:** Task 6's two tests
(`test_load_package_memoizes_within_a_process`, `test_load_package_cache_invalidates_on_mtime_change`
in `uedcli/tests/test_upackage.py`) do not set `UEDCLI_HOME`/`UEDCLI_PKG_CACHE`. Once this task's
on-disk tier exists, those tests would read/write the REAL `~/.uedcli/cache/pkg/` directory on
whatever host runs them — test pollution of a real user directory. Add
`monkeypatch.setenv("UEDCLI_PKG_CACHE", "off")` to both tests (add a `monkeypatch` parameter to
`test_load_package_cache_invalidates_on_mtime_change`, which doesn't currently take one) so they
exercise ONLY the in-process tier, matching what they were written to test.

- [ ] **Step 7: Run all of `test_pkg_cache.py` and `test_upackage.py`, verify green**

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_pkg_cache.py uedcli/tests/test_upackage.py -v`
Expected: all pass, including Task 6's memoization tests (still valid — the on-disk tier sits
below the in-process one, doesn't change its behavior for a single process's repeat calls).

- [ ] **Step 8: Commit**

```bash
git add uedcli/pkg_cache.py uedcli/config.py uedcli/upackage.py uedcli/tests/test_pkg_cache.py
git commit -m "Add on-disk package cache tier (mirrors schema_cache.py's scheme)"
```

---

### Task 8: Corpus parity test (migration guard, deleted after this plan merges)

**Files:**
- Create (temporary): `uedcli/tests/test_upackage_rust_parity.py`

**Interfaces:**
- Consumes: `uedcli.upackage.load_package` (the NEW Rust-backed version).
- Produces: nothing durable — this file is a one-time migration guard, per the spec's own
  "Tests" section ("run once, delete after PR 1 merges — it's a migration guard, not a durable
  test"). Task 9's final step deletes it.

Since the Python-side old decoder is DELETED in Task 5 (not kept side-by-side), this can't be a
literal "old output == new output" diff test run at the same time. Instead: capture the git blob of
`upackage.py` from BEFORE Task 5's commit, run ITS decoder against the same real corpus files
Task 5's broader test run already exercises, and compare.

- [ ] **Step 1: Find the pre-Task-5 commit**

Run: `git log --oneline -- uedcli/upackage.py | head -20` and identify the commit immediately
before Task 5's "Rewire upackage.py's table walk onto the Rust core" commit.

- [ ] **Step 2: Write the parity test**

Create `uedcli/tests/test_upackage_rust_parity.py`:

```python
"""Migration guard: confirms the Rust-backed upackage.py decodes every available real package
fixture identically to the pre-migration pure-Python decoder. Run once before this plan's final
merge; DELETE this file as part of that merge (dev/docs/rules/documentation.md: specs/plans/
migration-guard tests are ephemeral, not durable coverage) -- do not leave it in the tree."""
import subprocess
import sys

import pytest

PRE_MIGRATION_SHA = "REPLACE-WITH-THE-COMMIT-SHA-FROM-STEP-1"


def _old_parse_package_bytes():
    """Load upackage.parse_package_bytes as it existed before the Rust rewrite, via a subprocess
    checkout into an isolated import -- avoids fighting import-system caching of the CURRENT
    upackage module within this same test process."""
    src = subprocess.run(
        ["git", "show", f"{PRE_MIGRATION_SHA}:uedcli/upackage.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    ns: dict = {"__name__": "upackage_old"}
    exec(compile(src, "upackage_old.py", "exec"), ns)
    return ns["parse_package_bytes"]


@pytest.fixture(scope="module")
def old_parse():
    return _old_parse_package_bytes()


def _corpus_files():
    import pathlib
    roots = [pathlib.Path("/workspace/dx_lum/Maps")]
    for root in roots:
        if root.exists():
            yield from root.glob("*.dx")
            yield from root.glob("*.u")
            yield from root.glob("*.utx")


@pytest.mark.parametrize("path", list(_corpus_files()), ids=lambda p: p.name)
def test_rust_decode_matches_pre_migration_python_decode(path, old_parse):
    buf = path.read_bytes()
    from uedcli.upackage import parse_package_bytes as new_parse
    old_pkg = old_parse(buf, where=str(path))
    new_pkg = new_parse(buf, where=str(path))
    assert new_pkg.version == old_pkg.version
    assert new_pkg.names == old_pkg.names
    assert new_pkg.imports == old_pkg.imports
    assert new_pkg.exports == old_pkg.exports
```

If `_corpus_files()` finds nothing on this host (no real fixtures installed), the parametrize
collects zero test cases — that's an acceptable outcome for THIS host, but before treating Task 8
as done, run it explicitly on a host/session where the fixtures ARE present (check
`dev_docs/rules/tests.md` or ask whether this session has access to a fixture-bearing host; if
not, note this explicitly in the final report rather than silently treating "zero cases ran" as
"parity confirmed").

- [ ] **Step 3: Fill in `PRE_MIGRATION_SHA`, run the test**

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s uedcli/tests/test_upackage_rust_parity.py -v`
Expected: every collected case passes. If ANY fixture disagrees, STOP — this is a real behavioral
regression in Tasks 1-5's Rust port, not something to mask or skip. Root-cause and fix the Rust
code (most likely culprit: a table-walk field-order mistake, or the DoS guard rejecting a real
large-but-valid package — check the guard's `count > buf.len()` bound against the actual failing
file's real counts before assuming the guard itself is wrong).

- [ ] **Step 4: Do NOT commit this file yet** — it gets deleted in Task 9's final step. Leave it
  uncommitted (or commit-then-revert) so Task 9 can `git rm` it cleanly.

---

### Task 9: Full regression pass, cleanup, and final verification

**Files:** none new — this task runs the broader suite and fixes anything Task 8 didn't already
catch, then removes the temporary parity test.

- [ ] **Step 1: Run the full non-integration suite once** (per `dev/docs/rules/tests.md`: scope
  during iteration, run the whole suite once before the final commit)

Run: `TMPDIR=$PWD/_scratch/pt bin/test -p no:cacheprovider -o cache_dir=_scratch/pt/pc -s`

Expected: green, except the two pre-existing reds this project's docs already name as unrelated
(`test_doc_links`, `test_native_lit_room_ships_light_export_refs` — confirm these are still the
ONLY reds by diffing the failure list against a run on `master` before this plan's first commit;
if a NEW test fails, that's this plan's regression to fix, not a pre-existing one to wave off).

- [ ] **Step 2: `cargo test` for the whole `uedcli-native` crate one more time**

Run: whatever `bin/_venv.sh` invokes (same command as Task 4 Step 3).
Expected: green, including every test this plan added.

- [ ] **Step 3: Read the full diff**

Run: `git diff origin/master...HEAD --stat` then read the actual diff of `uedcli/upackage.py`,
`uedcli-native/src/package_read.rs`, and `uedcli-native/src/lib.rs` in full. Confirm:
- No caller outside `upackage.py`/`pkg_cache.py` was touched (Global Constraints: PR2's job).
- `Package.names` really is untouched `list[str]` everywhere it's read.
- No leftover `TODO`/debug `print`/commented-out old code.

- [ ] **Step 4: Delete the migration-guard test**

```bash
git rm uedcli/tests/test_upackage_rust_parity.py
```
(Only after Task 8 Step 3 actually ran green on real fixtures — don't delete it if that
verification never happened; escalate that gap instead of silently dropping the check.)

- [ ] **Step 5: Update the board item**

Edit `dev/docs/board/to-plan/unify-ue1-package-read-primitives-into-one-rust/overview.md` to note
PR1 is done and PR2 (retiring `dxpkg.py`/`utexture.py`/`proceduraltex.py`/`gate.py`/
`native/pkg_write.py` onto this core) is a separate, later plan — then `git mv` the item to
`dev/docs/board/to-build/` is NOT correct here (PR1 isn't "ready to build", it's built) — instead
follow this project's actual runbook: this plan's execution IS the build, so once merged, `git mv`
the item to `dev/docs/board/done/` with a short reference line per `building-features.md`'s
runbook, noting PR2 remains as a fresh `to-spec`/`to-plan` item to file separately (don't invent
its plan now — that's future work, scoped and planned when it's picked up).

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "Delete migration-guard parity test; close PR1 of the package-read-core item"
```

---

## Self-review notes (from writing this plan)

- **Spec coverage**: every spec.md section has a task — Rust core (Tasks 1-3), PyO3 binding
  (Task 4), Python shell (Task 5), caching both tiers (Tasks 6-7), migration-guard testing
  (Task 8), final verification (Task 9). PR2 (retiring the other 5 duplicate parsers) is
  explicitly OUT of this plan's scope, per the spec's own PR1/PR2 split — file it as its own
  board item + plan once PR1 is merged and stable.
- **Two corrections made to the merged spec during this planning pass** (both already edited into
  `spec.md`, with their own commits): the `RawPackage.imports` type (was wrongly `String` for the
  4th field, is actually `i64`), and the `Package.names`/`NameEntry` design (was "merge into
  tuples, migrate ~15 callers"; is now "add `name_entries` alongside untouched `names`" after
  finding the real caller count is 65+, not ~15).
- **Open verification gap, flagged not hidden**: Task 8's real-corpus parity run depends on
  fixtures (`/workspace/dx_lum/Maps/*.dx`, installed DX assets) that may or may not exist on
  whatever host executes this plan. If they don't, Task 8 collects zero parametrized cases —
  which is NOT the same as "parity confirmed" and must be reported as a gap, not silently passed
  over, per this project's "no silent half-answers" rule.
