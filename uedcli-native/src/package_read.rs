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
        if pos > buf.len() {
            return Err(BuildError(format!("name entry at {pos}: buffer overrun at byte {pos}")));
        }
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

    #[test]
    fn read_name_v61_buffer_overrun_at_pos() {
        // Test critical bug fix: pos > buf.len() should error, not panic
        let buf = b"short".to_vec();
        let err = read_name(&buf, 100, 61).unwrap_err();
        assert!(err.0.contains("buffer overrun"), "message: {}", err.0);
    }

    #[test]
    fn read_name_v69_truncated_after_length() {
        // Length says 10 bytes, but buffer ends after 3
        let mut buf = vec![0x0au8]; // compact index 10
        buf.extend_from_slice(b"Foo"); // only 3 bytes, not 10
        let err = read_name(&buf, 0, 69).unwrap_err();
        assert!(err.0.contains("overruns buffer"), "message: {}", err.0);
    }

    #[test]
    fn read_fstring_buffer_overrun() {
        // Length says 10 bytes, but buffer ends after 3
        let mut buf = vec![0x0au8]; // compact index 10
        buf.extend_from_slice(b"Foo"); // only 3 bytes, not 10
        let err = read_fstring(&buf, 0).unwrap_err();
        assert!(err.0.contains("overruns buffer"), "message: {}", err.0);
    }

    #[test]
    fn read_array_index_two_byte_form_truncated() {
        // Two-byte form (0x80 <= b0 < 0xC0) but only 1 byte in buffer
        let err = read_array_index(&[0x80], 0).unwrap_err();
        assert!(err.0.contains("buffer overrun"), "message: {}", err.0);
    }

    #[test]
    fn read_array_index_four_byte_form_truncated() {
        // Four-byte form (b0 >= 0xC0) but only 2 bytes in buffer
        let err = read_array_index(&[0xC0, 0x01], 0).unwrap_err();
        assert!(err.0.contains("buffer overrun"), "message: {}", err.0);
    }
}

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
        // Build a v61-compatible package (no GUID, null-terminated names)
        let mut names_blob = Vec::new();
        names_blob.extend_from_slice(b"None"); // null-terminated string
        names_blob.push(0); // null terminator
        names_blob.extend_from_slice(&0u32.to_le_bytes()); // flags

        let name_offset = HEADER_FIXED; // v61 has no GUID
        let mut buf = vec![0u8; name_offset];
        buf[0..4].copy_from_slice(&MAGIC.to_le_bytes());
        buf[4..8].copy_from_slice(&61u32.to_le_bytes()); // version=61, licensee=0
        buf[8..12].copy_from_slice(&0u32.to_le_bytes()); // flags
        buf[12..16].copy_from_slice(&1u32.to_le_bytes()); // namecnt
        buf[16..20].copy_from_slice(&(name_offset as u32).to_le_bytes()); // nameoff
        buf[20..24].copy_from_slice(&0u32.to_le_bytes()); // expcnt
        buf[24..28].copy_from_slice(&(name_offset as u32 + names_blob.len() as u32).to_le_bytes()); // expoff
        buf[28..32].copy_from_slice(&0u32.to_le_bytes()); // impcnt
        buf[32..36].copy_from_slice(&(name_offset as u32 + names_blob.len() as u32).to_le_bytes()); // impoff
        buf.extend_from_slice(&names_blob);

        let pkg = parse_package(&buf).unwrap();
        assert_eq!(pkg.guid_range, None);
    }
}

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
