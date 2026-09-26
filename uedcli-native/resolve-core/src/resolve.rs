//! Resolved-class types: the shapes `resolve_class`/`resolve_actor_props` (Tasks 4-5) produce, and
//! their hand-written `Serialize` impls matching the parent spec's exact wire contract (spec §4).
//! Also `ResolutionContext` (Task 3): the stateful, push-based package cache both callers walk
//! their closure through before resolving a class. `resolve_class` (Task 4) and
//! `resolve_actor_props` (Task 5), built on top of it, are both below.

use crate::package_read::{self, RawPackage};
use serde::{Serialize, Serializer};
use std::collections::BTreeMap;

#[derive(Clone, Debug, Serialize)]
pub struct ResolvedClass {
    pub props: Vec<ResolvedProp>,
}

#[derive(Clone, Debug)]
pub enum ResolvedProp {
    Scalar { name: String, category: String, kind: ScalarKind, default_value: String },
    Enum { name: String, category: String, enum_type: String, default_value: String },
    Struct { name: String, category: String, struct_type: String, default_value: DefaultValue },
    Array {
        name: String,
        category: String,
        array_dim: u32,
        element: ArrayElementKind,
        default_value: Vec<DefaultValue>,
    },
}

// A derive can't produce this shape: `Scalar`'s own `kind: ScalarKind` field collides with the
// outer discriminant, and `Struct`/`Array` need different field SETS, not just different tag
// values. Hand-write it, one branch per variant (spec §4).
impl Serialize for ResolvedProp {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut m = s.serialize_map(None)?;
        match self {
            ResolvedProp::Scalar { name, category, kind, default_value } => {
                m.serialize_entry("kind", kind)?; // ScalarKind's own Serialize gives "int"/"float"/etc.
                m.serialize_entry("name", name)?;
                m.serialize_entry("category", category)?;
                m.serialize_entry("default_value", default_value)?;
            }
            ResolvedProp::Enum { name, category, enum_type, default_value } => {
                m.serialize_entry("kind", "enum")?;
                m.serialize_entry("name", name)?;
                m.serialize_entry("category", category)?;
                m.serialize_entry("enum_type", enum_type)?;
                m.serialize_entry("default_value", default_value)?;
            }
            ResolvedProp::Struct { name, category, struct_type, default_value } => {
                m.serialize_entry("kind", "struct")?;
                m.serialize_entry("name", name)?;
                m.serialize_entry("category", category)?;
                m.serialize_entry("struct_type", struct_type)?;
                m.serialize_entry("default_value", default_value)?;
            }
            ResolvedProp::Array { name, category, array_dim, element, default_value } => {
                m.serialize_entry("kind", "array")?;
                m.serialize_entry("name", name)?;
                m.serialize_entry("category", category)?;
                m.serialize_entry("array_dim", array_dim)?;
                match element {
                    ArrayElementKind::Scalar(k) => m.serialize_entry("element_kind", k)?,
                    ArrayElementKind::Enum(key) => m.serialize_entry("element_type", key)?,
                    ArrayElementKind::Struct(key) => m.serialize_entry("element_type", key)?,
                }
                m.serialize_entry("default_value", default_value)?;
            }
        }
        m.end()
    }
}

// The real, closed vocabulary -- these strings ARE the wire contract (spec §1/§3). `StringKind`
// is the one non-obvious rename: `String` collides with the Rust prelude type.
#[derive(Clone, Copy, Debug)]
pub enum ScalarKind {
    Float,
    Int,
    Bool,
    Byte,
    Name,
    StringKind,
}

impl Serialize for ScalarKind {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        let text = match self {
            ScalarKind::Float => "float",
            ScalarKind::Int => "int",
            ScalarKind::Bool => "bool",
            ScalarKind::Byte => "byte",
            ScalarKind::Name => "name",
            ScalarKind::StringKind => "string",
        };
        s.serialize_str(text)
    }
}

#[derive(Clone, Debug)]
pub enum ArrayElementKind {
    Scalar(ScalarKind), // element_kind: "<scalar kind>", no type reference
    Enum(String),       // element_type: "<enum type key>" -- types[key]["kind"] == "enum"
    Struct(String),     // element_type: "<struct type key>" -- types[key]["kind"] == "struct"
}

// Serialize-only, one direction -- untagged serialization doesn't need shape-distinguishability
// (that only matters for untagged DESERIALIZATION, which this type never does). Debug/PartialEq
// are for tests (Task 4's own struct/array default-value assertions) -- not needed by any
// production caller.
#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(untagged)]
pub enum DefaultValue {
    Scalar(String),
    Struct(BTreeMap<String, DefaultValue>),
    Array(Vec<DefaultValue>),
}

#[derive(Clone, Debug)]
pub enum TypeShape {
    Struct { members: Vec<TypeMember> },
    Enum { values: Vec<String> }, // ordered, ordinal = index
}

impl Serialize for TypeShape {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut m = s.serialize_map(None)?;
        match self {
            TypeShape::Struct { members } => {
                m.serialize_entry("kind", "struct")?;
                m.serialize_entry("members", members)?;
            }
            TypeShape::Enum { values } => {
                m.serialize_entry("kind", "enum")?;
                m.serialize_entry("values", values)?;
            }
        }
        m.end()
    }
}

#[derive(Clone, Debug)]
pub struct TypeMember {
    pub name: String,
    pub kind: MemberKind,
}

// The real vocabulary, matching the parent spec's per-kind field naming exactly (never a shared
// generic "type" field). NOT symmetric with `ResolvedProp::Array` (spec §2): a `ScalarArray`
// member emits `{"kind": "<scalar kind>", "array_dim": N}` -- "kind" IS the scalar kind directly,
// "array" is never the literal kind string here, and there is no `element_kind` field at all;
// only `StructArray`/`EnumArray` emit `{"kind":"array","array_dim":N,"element_type":"<key>"}`.
#[derive(Clone, Debug)]
pub enum MemberKind {
    Scalar(ScalarKind),                              // wire: "kind": "<scalar kind>"
    ScalarArray { array_dim: u32, kind: ScalarKind }, // wire: "kind": "<scalar kind>", "array_dim": N
    Struct { struct_type: String },                  // wire: "kind":"struct", "struct_type": "<key>"
    Enum { enum_type: String },                      // wire: "kind":"enum", "enum_type": "<key>"
    StructArray { array_dim: u32, struct_type: String }, // wire: "kind":"array", "array_dim": N, "element_type": "<key>"
    EnumArray { array_dim: u32, enum_type: String },     // wire: "kind":"array", "array_dim": N, "element_type": "<key>"
}

impl MemberKind {
    /// Writes this variant's own fields into an already-open map, so `TypeMember`'s `Serialize`
    /// can emit `kind`/`name`/etc. as SIBLINGS in one flat object rather than nesting `MemberKind`
    /// under a `"kind"` key (a plain derive on `TypeMember` would double-nest).
    fn write_fields<M: serde::ser::SerializeMap>(&self, m: &mut M) -> Result<(), M::Error> {
        match self {
            MemberKind::Scalar(k) => m.serialize_entry("kind", k),
            MemberKind::ScalarArray { array_dim, kind } => {
                m.serialize_entry("kind", kind)?;
                m.serialize_entry("array_dim", array_dim)
            }
            MemberKind::Struct { struct_type } => {
                m.serialize_entry("kind", "struct")?;
                m.serialize_entry("struct_type", struct_type)
            }
            MemberKind::Enum { enum_type } => {
                m.serialize_entry("kind", "enum")?;
                m.serialize_entry("enum_type", enum_type)
            }
            MemberKind::StructArray { array_dim, struct_type } => {
                m.serialize_entry("kind", "array")?;
                m.serialize_entry("array_dim", array_dim)?;
                m.serialize_entry("element_type", struct_type)
            }
            MemberKind::EnumArray { array_dim, enum_type } => {
                m.serialize_entry("kind", "array")?;
                m.serialize_entry("array_dim", array_dim)?;
                m.serialize_entry("element_type", enum_type)
            }
        }
    }
}

// Used nowhere directly -- `MemberKind` is never serialized on its own outside a `TypeMember`.
impl Serialize for MemberKind {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut m = s.serialize_map(None)?;
        self.write_fields(&mut m)?;
        m.end()
    }
}

impl Serialize for TypeMember {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        use serde::ser::SerializeMap;
        let mut m = s.serialize_map(None)?;
        self.kind.write_fields(&mut m)?;
        m.serialize_entry("name", &self.name)?;
        m.end()
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct ClassResolution {
    pub class: ResolvedClass,
    pub types: BTreeMap<String, TypeShape>, // only types THIS class's shape references
}

// Plain derive is correct here -- no tagged-union/XOR shape, unlike ResolvedProp/TypeMember
// above; wire shape is {"sparse": {...}, "note": null|"..."}. Clone per spec §2:215-216 (the
// plan's own Step 7 code sample dropped it; spec is the binding authority on conflict).
#[derive(Clone, Serialize)]
pub struct ActorResolution {
    pub sparse: BTreeMap<String, String>,
    pub note: Option<String>,
}

#[derive(Debug)]
pub enum ResolveError {
    UnresolvableClass(String),
    MissingPackage(String),
    MalformedSchema { class: String, reason: String },
    MalformedPackage { name: String, reason: String },
}

impl std::fmt::Display for ResolveError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ResolveError::UnresolvableClass(name) => write!(f, "class not found: {name}"),
            ResolveError::MissingPackage(name) => write!(f, "package not added: {name}"),
            ResolveError::MalformedSchema { class, reason } => {
                write!(f, "malformed schema for class {class}: {reason}")
            }
            ResolveError::MalformedPackage { name, reason } => {
                write!(f, "malformed package {name}: {reason}")
            }
        }
    }
}

/// The stateful, push-based cache callers add raw `.u` package bytes to. `add_package` parses and
/// caches internally; `resolve_class`/`resolve_actor_props` (Task 4) read from `packages` and write
/// `class_cache`. See spec §3.
pub struct ResolutionContext {
    packages: BTreeMap<String, (RawPackage, Vec<u8>)>,
    class_cache: BTreeMap<String, ClassResolution>,
    resolutions_performed: usize,
    poisoned: bool,
    poison_reason: String,
}

impl ResolutionContext {
    pub fn new() -> Self {
        ResolutionContext {
            packages: BTreeMap::new(),
            class_cache: BTreeMap::new(),
            resolutions_performed: 0,
            poisoned: false,
            poison_reason: String::new(),
        }
    }

    /// Cache-hit counter Task 4's `resolve_class` increments on an actual (non-cached) Super-chain
    /// walk. Read-only here; this task only owns the field and its accessor.
    pub fn resolutions_performed(&self) -> usize {
        self.resolutions_performed
    }

    /// TRUE if `name` has already been added. Once poisoned, always reports `false` -- its own
    /// `-> bool` signature has no error channel to signal "poisoned" through instead.
    pub fn has_package(&self, name: &str) -> bool {
        if self.poisoned {
            return false;
        }
        self.packages.contains_key(name)
    }

    /// Parses `buf` via `package_read::parse_package` and stores both the parsed table and the
    /// owned bytes. Idempotent: a cheap no-op if `name` is already present. On ANY parse failure,
    /// poisons the context (spec §3's flagged abort-path hole) before returning the error.
    pub fn add_package(&mut self, name: &str, buf: Vec<u8>) -> Result<(), ResolveError> {
        if self.poisoned {
            return Err(ResolveError::MalformedPackage {
                name: "<poisoned>".into(),
                reason: self.poison_reason.clone(),
            });
        }
        if self.packages.contains_key(name) {
            return Ok(());
        }
        match crate::package_read::parse_package(&buf) {
            Ok(raw) => {
                self.packages.insert(name.to_string(), (raw, buf));
                Ok(())
            }
            Err(e) => {
                let reason = e.to_string();
                self.poison(reason.clone());
                Err(ResolveError::MalformedPackage { name: name.to_string(), reason })
            }
        }
    }

    /// Pure query over an already-added package's own import table, filtered to Class/Struct/Enum-
    /// typed imports or a `*Property` type reference, resolved to the owning package name via the
    /// import's outer chain (`import_package_of`). Returns package names, deduped and sorted.
    pub fn package_imports(&self, name: &str) -> Result<Vec<String>, ResolveError> {
        if self.poisoned {
            return Err(ResolveError::MalformedPackage {
                name: "<poisoned>".into(),
                reason: self.poison_reason.clone(),
            });
        }
        let (raw, _bytes) = self
            .packages
            .get(name)
            .ok_or_else(|| ResolveError::MissingPackage(name.to_string()))?;
        let mut out = std::collections::BTreeSet::new();
        for (idx, (_class_pkg, class_name, _pkg_idx, _obj_name)) in raw.imports.iter().enumerate() {
            let Some(class_name_text) = raw.names.get(usize::try_from(*class_name).unwrap_or(usize::MAX)).map(|(t, _)| t.as_str()) else {
                continue;
            };
            let keep = class_name_text == "Class"
                || class_name_text == "Struct"
                || class_name_text == "Enum"
                || class_name_text.ends_with("Property");
            if !keep {
                continue;
            }
            if let Some(pkg) = import_package_of(raw, idx) {
                out.insert(pkg);
            }
        }
        Ok(out.into_iter().collect())
    }

    /// Degrades the context permanently: every subsequent Result-returning call errors, and
    /// `has_package` reports `false` regardless of what was added before poisoning. Public because
    /// a caller OUTSIDE this crate's own control flow (the Python `_populate_for_class` closure
    /// walk, spec §3) can abort mid-walk for a reason this crate's own code never triggers -- a
    /// missing package on the caller's search path, raised before any `add_package` call ever
    /// reaches Rust -- and must be able to poison the context itself so a package added before the
    /// abort never silently reports `has_package` truthy with its own imports unwalked.
    pub fn poison(&mut self, reason: String) {
        self.poisoned = true;
        self.poison_reason = reason;
    }
}

impl Default for ResolutionContext {
    fn default() -> Self {
        Self::new()
    }
}

/// The owning package name of import `import_idx0` (0-based), by walking the outer chain
/// (`package_index`) to its root. Direct Rust port of the reference implementation's
/// `Package.import_package_of` (`uedcli/upackage.py:125-137`): `package_index == 0` means this
/// import's own `object_name` (resolved via the name table) IS the package name; `package_index <
/// 0` follows `imports[-package_index - 1]` (0-based) and repeats; `package_index > 0` is not a
/// valid outer for an import (only exports use a positive outer) -- unresolvable, same as the
/// Python reference. Bounded at 64 iterations (matching the Python reference's own cycle guard);
/// an out-of-range index or a walk that doesn't terminate within the bound returns `None` rather
/// than panicking or looping forever.
fn import_package_of(raw: &RawPackage, import_idx0: usize) -> Option<String> {
    let mut cur = raw.imports.get(import_idx0)?;
    for _ in 0..64 {
        let (_class_pkg, _class_name, package_index, object_name) = cur;
        if *package_index == 0 {
            return raw
                .names
                .get(usize::try_from(*object_name).ok()?)
                .map(|(t, _)| t.clone());
        }
        if *package_index < 0 {
            let next_idx = usize::try_from(-*package_index - 1).ok()?;
            cur = raw.imports.get(next_idx)?;
        } else {
            return None;
        }
    }
    None
}

const EX_END_FUNCTION_PARMS: u8 = 0x16;

/// Tracks a script-bytecode replay's disk position (`pos`) and in-memory size accumulated so
/// far (`mem`) -- the two diverge only for compact-encoded refs (variable-width disk, fixed 4
/// bytes in memory), which is the WHOLE reason this walk exists (`ScriptSize` is `mem`, not the
/// on-disk byte count). `names` is the package's own name table, needed by ONE opcode
/// (LabelTable, 0x0C) to detect its own "None" terminator. Direct port of `uprops/ufield.py:112-
/// 260`'s `_walk_expr`/`_skip_script` (Task 4 Step 0.5).
struct ScriptCursor<'a> { buf: &'a [u8], names: &'a [String], pos: usize, mem: usize }

impl<'a> ScriptCursor<'a> {
    fn obj(&mut self) -> Result<(), ResolveError> {   // object ref: compact disk / 4 bytes mem
        let (_v, next) = package_read::read_compact_index(self.buf, self.pos)
            .map_err(|e| ResolveError::MalformedPackage { name: "<script>".into(), reason: e.0 })?;
        self.pos = next;
        self.mem += 4;
        Ok(())
    }
    fn name(&mut self) -> Result<(), ResolveError> { self.obj() } // same shape: compact disk / 4 mem
    fn fixed(&mut self, n: usize) { self.pos += n; self.mem += n; } // same size disk and mem
    fn expr(&mut self) -> Result<u8, ResolveError> { walk_expr(self) }
    fn parms(&mut self) -> Result<(), ResolveError> {   // function args until EX_EndFunctionParms
        loop { if self.expr()? == EX_END_FUNCTION_PARMS { return Ok(()); } }
    }
    fn byte_at(&self, p: usize) -> Result<u8, ResolveError> {
        self.buf.get(p).copied().ok_or_else(|| ResolveError::MalformedPackage {
            name: "<script>".into(), reason: format!("script opcode read overrun at {p}") })
    }
    fn u16_at(&self, p: usize) -> Result<u16, ResolveError> {
        Ok(u16::from_le_bytes([self.byte_at(p)?, self.byte_at(p + 1)?]))
    }
}

/// Replays ONE `SerializeExpr` (direct port of `ufield.py:112-248`'s `_walk_expr` match/elif
/// chain, translated arm-for-arm, same opcode values). Returns the token read (matching the
/// Python return's third element).
fn walk_expr(c: &mut ScriptCursor) -> Result<u8, ResolveError> {
    let tok = c.byte_at(c.pos)?;
    c.pos += 1; c.mem += 1;
    match tok {
        t if t >= 0x70 => c.parms()?,                          // single-byte native call index
        t if t >= 0x60 => { c.fixed(1); c.parms()?; }           // extended native
        t if (0x39..=0x5F).contains(&t) => { c.expr()?; }        // conversion tokens
        0x00 | 0x01 | 0x02 => c.obj()?,                         // Local/Instance/DefaultVariable
        0x04 => { c.expr()?; }                                  // Return
        0x05 => { c.fixed(1); c.expr()?; }                      // Switch
        0x06 => c.fixed(2),                                     // Jump: u16
        0x07 => { c.fixed(2); c.expr()?; }                      // JumpIfNot
        0x08 => {}                                              // Stop
        0x09 => { c.fixed(2); c.expr()?; }                      // Assert
        0x0A => {                                               // Case: u16 next; 0xFFFF == default
            let w = c.u16_at(c.pos)?;
            c.fixed(2);
            if w != 0xFFFF { c.expr()?; }
        }
        0x0B => {}                                              // Nothing
        0x0C => loop {                                          // LabelTable: {name,u32} until "None"
            let (v, next) = package_read::read_compact_index(c.buf, c.pos)
                .map_err(|e| ResolveError::MalformedPackage { name: "<script>".into(), reason: e.0 })?;
            c.pos = next; c.mem += 4;
            let nm = usize::try_from(v).ok().and_then(|i| c.names.get(i));
            c.fixed(4);
            if nm.map(|s| s.as_str()) == Some("None") { break; }
        },
        0x0D => { c.expr()?; }                                  // GotoLabel
        0x0E => { c.expr()?; }                                  // EatString
        0x0F | 0x14 => { c.expr()?; c.expr()?; }                // Let / LetBool
        0x11 => { c.expr()?; c.expr()?; c.expr()?; c.expr()?; } // New: 4 exprs
        0x12 => { c.expr()?; c.fixed(3); c.expr()?; }           // ClassContext
        0x13 => { c.obj()?; c.expr()?; }                        // MetaCast
        0x16 => {}                                              // EndFunctionParms
        0x17 => {}                                              // Self
        0x18 => { c.fixed(2); c.expr()?; }                      // Skip
        0x19 => { c.expr()?; c.fixed(3); c.expr()?; }           // Context
        0x1A => { c.expr()?; c.expr()?; }                       // ArrayElement
        0x1B => { c.name()?; c.parms()?; }                      // VirtualFunction
        0x1C => { c.obj()?; c.parms()?; }                       // FinalFunction
        0x1D => c.fixed(4),                                     // IntConst
        0x1E => c.fixed(4),                                     // FloatConst
        0x1F => {                                               // StringConst: NUL-terminated
            let tail = c.buf.get(c.pos..).ok_or_else(|| ResolveError::MalformedPackage {
                name: "<script>".into(), reason: format!("script opcode read overrun at {}", c.pos) })?;
            let end = tail.iter().position(|&b| b == 0)         // `.get()` first -- a plain slice
                .ok_or_else(|| ResolveError::MalformedPackage {  // index (`c.buf[c.pos..]`) panics
                    name: "<script>".into(), reason: format!("unterminated StringConst at {}", c.pos) })?; // if c.pos > buf.len(), unlike every other read in this walker.
            c.fixed(end + 1);
        }
        0x20 => c.obj()?,                                       // ObjectConst
        0x21 => c.name()?,                                      // NameConst
        0x22 | 0x23 => c.fixed(12),                             // RotationConst / VectorConst
        0x24 => c.fixed(1),                                     // ByteConst
        0x25 | 0x26 | 0x27 | 0x28 => {}                         // IntZero/IntOne/True/False
        0x29 => c.obj()?,                                       // NativeParm
        0x2A => {}                                              // NoObject
        0x2C => c.fixed(1),                                     // IntConstByte
        0x2D => { c.expr()?; }                                  // BoolVariable
        0x2E => { c.obj()?; c.expr()?; }                        // DynamicCast
        0x2F => { c.expr()?; c.fixed(2); }                      // Iterator
        0x30 | 0x31 => {}                                       // IteratorPop / IteratorNext
        0x32 | 0x33 => { c.obj()?; c.expr()?; c.expr()?; }      // StructCmpEq/Ne
        0x34 => loop {                                          // UnicodeStringConst: u16 units until 0
            let w = c.u16_at(c.pos)?;
            c.fixed(2);
            if w == 0 { break; }
        },
        0x36 => { c.obj()?; c.expr()?; }                        // StructMember
        0x38 => { c.name()?; c.parms()?; }                      // GlobalFunction
        _ => return Err(ResolveError::MalformedPackage {
            name: "<script>".into(),
            reason: format!("unknown script opcode {tok:#04x} at {}", c.pos - 1),
        }),
    }
    Ok(tok)
}

/// Walks the whole script blob (in-memory size `script_size`), returning the disk position
/// after it. Direct port of `ufield.py:251-260`'s `_skip_script`.
fn skip_script(buf: &[u8], names: &[String], pos: usize, script_size: usize)
    -> Result<usize, ResolveError> {
    let mut c = ScriptCursor { buf, names, pos, mem: 0 };
    while c.mem < script_size { walk_expr(&mut c)?; }
    if c.mem != script_size {
        return Err(ResolveError::MalformedPackage {
            name: "<script>".into(),
            reason: format!("script walk desync: memory cursor {} != ScriptSize {script_size}", c.mem),
        });
    }
    Ok(c.pos)
}

/// Direct port of `uclass.py:294-322`'s `class_default_tags`: walks a UClass export's OWN body
/// (per the field order `class_body_header`, Step 0, already documents) to find and decode its
/// defaults tag block. `buf`/`names` are the OWNING package's; `soff`/`ssize` are this class's
/// own export entry fields. Returns the decoded tags (the SAME `RawPropertyTag` shape
/// `read_property_tags` already returns elsewhere) or a `ResolveError` naming the desync.
fn class_default_tags(buf: &[u8], names: &[String], soff: i64, ssize: i64)
    -> Result<Vec<package_read::RawPropertyTag>, ResolveError> {
    if ssize <= 0 { return Ok(Vec::new()); }  // an intrinsic class with no body: no defaults
    let end = (soff + ssize) as usize;
    let mut p = soff as usize;
    let mk_err = |reason: String| ResolveError::MalformedPackage { name: "<class body>".into(), reason };
    let (_sup, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next;   // SuperField
    let (_next_f, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next; // UField.Next
    let (_st, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next;    // ScriptText
    let (_children, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next; // Children
    let (_fname, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next; // FriendlyName
    p += 8; // Line:u32 + TextPos:u32
    let script_size = u32::from_le_bytes(buf.get(p..p+4).ok_or_else(|| mk_err("truncated ScriptSize".into()))?.try_into().unwrap()) as usize;
    p += 4;
    p = skip_script(buf, names, p, script_size)?; // Step 0.5's script-bytecode walker
    p += 8 + 8 + 2 + 4;   // UState: ProbeMask + IgnoreMask + LabelTableOffset + StateFlags
    p += 4 + 16;           // UClass: ClassFlags + ClassGuid
    let (depcnt, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next;
    for _ in 0..depcnt {
        let (_cls, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next;
        p += 8; // Deep:u32 + ScriptTextCRC:u32
    }
    let (impcnt, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next;
    for _ in 0..impcnt {
        let (_n, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next;
    }
    let (_within, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next;  // ClassWithin
    let (_cfg, next) = package_read::read_compact_index(buf, p).map_err(|e| mk_err(e.0))?; p = next;      // ClassConfigName
    let (tags, p_after) = package_read::read_property_tags(buf, p, end, names)
        .map_err(|e| mk_err(e.0))?;
    if p_after != end {
        return Err(mk_err(format!("defaults did not consume to body end (cursor {p_after} != {end}, {} bytes left)", end - p_after)));
    }
    Ok(tags)
}

// ═══ Task 4 Steps 1-5.7: resolve_class -- Super-chain walk, class-defaults decode, cross-package
// type_ref resolution, identity keying, the `types` closure ═══════════════════════════════════
//
// `TYPED_FIELDS` and positional array defaults are later steps (8-13, a separate sub-dispatch).
// Cross-package Super/type_ref resolution, `(package,outer,name)` identity keying (Step 5), and the
// `types` closure (Step 5.5, including struct super-chain recursion, Step 5.6) are implemented
// below. The Super-chain walk is written the same way `resolve_class_properties` itself is (a
// per-iteration fqcn split + package lookup), so it is not artificially restricted to same-package
// Super refs.

// The closed set of UProperty subclasses (`uprops/base.py:14-18`'s `PROPERTY_TYPES`).
const PROPERTY_TYPES: &[&str] = &[
    "ArrayProperty", "BoolProperty", "ByteProperty", "ClassProperty", "FloatProperty",
    "IntProperty", "NameProperty", "ObjectProperty", "PointerProperty", "StrProperty",
    "StructProperty",
];

// `uprops/base.py:21-23`'s `_KINDS_WITH_TYPE_REF`.
const KINDS_WITH_TYPE_REF: &[&str] =
    &["ByteProperty", "ObjectProperty", "StructProperty", "ClassProperty", "ArrayProperty"];

const CPF_NET: u32 = 0x20; // uprops/base.py:26 -- PropertyFlags bit: a 2-byte RepOffset follows Category

// A struct member of one of these kinds decodes (bytes consumed to keep the cursor in sync) but is
// OMITTED from the assembled `DefaultValue::Struct` map -- Step 6's exclusion chain, narrowed to
// what a struct member's own binary form can even represent (`_decode_struct_bin_at`,
// `values.py:179-181`; `ArrayProperty`/`PointerProperty` have no defined struct-member wire form at
// all and are a hard decode error below, matching Python's own `raise SchemaError` there).
const EXCLUDED_STRUCT_MEMBER_KINDS: &[&str] = &["ObjectProperty", "ClassProperty"];

// Step 6's own NAME-based exclusion chain -- applied ONLY at the top-level class-prop walk
// (`resolve_class_uncached`'s own loop, below), matching `effective_props.py:238-245`'s top-level
// loop exactly: none of these three recurse into struct members/array elements (only the KIND-based
// `_is_excluded_kind` does -- `EXCLUDED_STRUCT_MEMBER_KINDS` above for a struct member's binary
// decode, and `render_prop`'s own no-wire-shape `_ => Ok(None)` arm for a top-level/array-element
// prop). Matched case-folded (`.to_lowercase()`, this file's own convention).

// `uedcli/propedit/base.py:19`'s `HARD_REJECT` -- the actor Name, the Brush binding, and the
// mover-key geometry/view bookkeeping (`NumKeys` is deliberately NOT here, see that file's doc).
const HARD_REJECT: &[&str] = &["name", "brush", "keypos", "keyrot", "keynum"];

// `uedcli/propedit/fields.py:274-277`'s `TYPED_FIELDS` keys -- Location/MainScale/PostScale route
// through a separate typed-field emission path (Step 8, `render_typed_field`); excluded from the
// generic walk below so the class's OWN raw schema entry of the same name is never ALSO emitted as
// an ordinary prop.
const TYPED_FIELD_NAMES: &[&str] = &["location", "mainscale", "postscale"];

// Step 9's own ordering rule: these three, in THIS fixed order, always precede the generic walk's
// own output -- never the fixture's declaration order, never alphabetical.
const TYPED_FIELD_ORDER: &[&str] = &["location", "mainscale", "postscale"];

// `uedcli/normalize.py:103`'s `is_computed_key` -- its own `_INGEST_NAMES` (schema-free, matched by
// exact name) plus `_COMPUTED_PREFIXES` (matched by prefix). `_COMPUTED_GLOBAL`
// ("prevnavigationpoint") belongs to a DIFFERENT function (`is_authored_prop`) and is already a
// member of `_INGEST_NAMES` too, so it needs no separate entry here.
const INGEST_NAMES: &[&str] = &[
    "timeseconds", "summary", "region", "oldlocation", "navigationpointlist", "pawnlist",
    "nextnavigationpoint", "prevnavigationpoint", "level", "bselected", "basepos", "baserot",
    "savedpos", "savedrot",
];
const COMPUTED_PREFIXES: &[&str] = &["aiprofile"];

fn is_computed_key(name_lower: &str) -> bool {
    INGEST_NAMES.contains(&name_lower) || COMPUTED_PREFIXES.iter().any(|p| name_lower.starts_with(p))
}

/// A class or struct member's OWN schema (name/kind/category/array_dim/type_ref), plus the package
/// it was DECLARED in -- needed to resolve its `type_ref` via `resolve_type_export` (Step 5.7): a
/// positive `type_ref` is a local index into `declaring_pkg`'s own export table; a negative one is
/// an import, resolved to a DIFFERENT owning package's own table.
#[derive(Clone)]
struct DecodedProp {
    name: String,
    kind: String, // e.g. "IntProperty" -- the closed PROPERTY_TYPES vocabulary
    category: Option<String>,
    array_dim: u32,
    type_ref: i64,
    declaring_pkg: String,
}

/// Resolves a signed compact-object-reference's owning class NAME (0=None, >0=export's own `nm`,
/// <0=import's own `object_name`). Direct port of `upackage.py:110-123`'s `Package.name_of_ref`.
fn name_of_ref(raw: &RawPackage, names: &[String], idx: i64) -> Option<String> {
    if idx == 0 {
        return None;
    }
    if idx > 0 {
        let e = raw.exports.get((idx - 1) as usize)?;
        return names.get(e.nm as usize).cloned();
    }
    let j = (-idx - 1) as usize;
    let imp = raw.imports.get(j)?;
    names.get(imp.3 as usize).cloned()
}

/// 0-based export index of a UClass by name (case-insensitive). Direct port of
/// `class_export_index` (`uclass.py:15-21`).
fn find_class_export(raw: &RawPackage, names: &[String], class_name: &str) -> Option<usize> {
    let want = class_name.to_lowercase();
    for (i, e) in raw.exports.iter().enumerate() {
        if let Some(nm) = names.get(e.nm as usize) {
            if nm.to_lowercase() == want {
                let cls_name = name_of_ref(raw, names, e.cls);
                if cls_name.is_none() || cls_name.as_deref() == Some("Class") {
                    return Some(i);
                }
            }
        }
    }
    None
}

/// The direct super's FQCN, or `None` at the root. `sup > 0` is a local ref (same package); `sup <
/// 0` is an import, resolved via `import_package_of` (Task 3 Step 6). Direct port of `_super_fqcn`
/// (`uclass.py:73-90`).
fn super_fqcn(raw: &RawPackage, names: &[String], pkg_name: &str, class_idx0: usize)
    -> Result<Option<String>, ResolveError> {
    let e = &raw.exports[class_idx0];
    let sup = e.sup;
    if sup == 0 {
        return Ok(None);
    }
    if sup > 0 {
        let sup_e = raw.exports.get((sup - 1) as usize).ok_or_else(|| ResolveError::MalformedSchema {
            class: pkg_name.to_string(), reason: format!("super ref {sup} out of range"),
        })?;
        let sup_name = names.get(sup_e.nm as usize).cloned().unwrap_or_default();
        return Ok(Some(format!("{pkg_name}.{sup_name}")));
    }
    let j = (-sup - 1) as usize;
    let imp = raw.imports.get(j).ok_or_else(|| ResolveError::MalformedSchema {
        class: pkg_name.to_string(), reason: format!("import index {j} out of range for super ref"),
    })?;
    let super_name = names.get(imp.3 as usize).cloned().ok_or_else(|| ResolveError::MalformedSchema {
        class: pkg_name.to_string(), reason: "import object_name out of range".to_string(),
    })?;
    let super_pkg = import_package_of(raw, j).ok_or_else(|| ResolveError::MalformedSchema {
        class: pkg_name.to_string(),
        reason: format!("cannot resolve the owning package of imported super {super_name}"),
    })?;
    Ok(Some(format!("{super_pkg}.{super_name}")))
}

/// Finds a `want_class`-typed export ("Struct" or "Enum") by case-insensitive name. Direct port of
/// `find_struct_export` (`ufield.py:288-296`) generalized to the enum scan `resolve_type_export`
/// (`values.py:55-62`) also inlines for the non-Struct case -- same shape, one function covers both.
fn find_typed_export(raw: &RawPackage, names: &[String], type_name: &str, want_class: &str) -> Option<i64> {
    let want = type_name.to_lowercase();
    for (i, e) in raw.exports.iter().enumerate() {
        if name_of_ref(raw, names, e.cls).as_deref() == Some(want_class) {
            if let Some(nm) = names.get(e.nm as usize) {
                if nm.to_lowercase() == want {
                    return Some((i + 1) as i64);
                }
            }
        }
    }
    None
}

/// Resolves a `type_ref` to (owning package NAME, 1-based export index) -- direct port of
/// `resolve_type_export` (`values.py:23-65`), with ONE deliberate design difference: the real
/// Python LAZILY LOADS a not-yet-seen owning package (`resolver(...)` then `load_package(...)`);
/// this port NEVER loads on demand (spec §3's push-based model: every package this resolution could
/// need was already pushed via `add_package` before `resolve_class` was called) -- a missing owning
/// package is `ResolveError::MissingPackage(owner_pkg_name)`, matching every other cross-package
/// failure in this design. `declaring_pkg_name` is the package `_pkg_for_owner` resolves to (a
/// property's OWN declaring package, `DecodedProp::declaring_pkg` -- NOT necessarily the leaf
/// class's own package). `want_class` is `"Struct"` for a `StructProperty`'s own `type_ref`,
/// `"Enum"` for an enum-carrying `ByteProperty`'s -- NEVER called for `ObjectProperty`/
/// `ClassProperty`/`ArrayProperty` (all three are excluded kinds with no Struct/Enum `type_ref`
/// semantics of their own: `ArrayProperty`'s own `type_ref` is an export index to its `Inner`
/// UProperty, entirely different semantics; `Object`/`ClassProperty` point at a CLASS, out of this
/// project's own scope entirely).
fn resolve_type_export(ctx: &ResolutionContext, declaring_pkg_name: &str, type_ref: i64,
    want_class: &str) -> Result<(String, i64), ResolveError> {
    let (raw, _bytes) = ctx.packages.get(declaring_pkg_name)
        .ok_or_else(|| ResolveError::MissingPackage(declaring_pkg_name.to_string()))?;
    let names: Vec<String> = raw.names.iter().map(|(n, _)| n.clone()).collect();
    if type_ref > 0 {
        if type_ref as usize > raw.exports.len() {
            return Err(ResolveError::MalformedSchema { class: declaring_pkg_name.to_string(),
                reason: format!("{want_class} type ref {type_ref} out of range") });
        }
        return Ok((declaring_pkg_name.to_string(), type_ref));
    }
    if type_ref == 0 {
        return Err(ResolveError::MalformedSchema { class: declaring_pkg_name.to_string(),
            reason: format!("no {want_class} type ref to resolve") });
    }
    let j = (-type_ref - 1) as usize;
    let imp = raw.imports.get(j).ok_or_else(|| ResolveError::MalformedSchema {
        class: declaring_pkg_name.to_string(), reason: format!("import index {j} out of range") })?;
    let type_name = names.get(imp.3 as usize).cloned().ok_or_else(|| ResolveError::MalformedSchema {
        class: declaring_pkg_name.to_string(), reason: "import object_name out of range".into() })?;
    let owner_pkg_name = import_package_of(raw, j).ok_or_else(|| ResolveError::MalformedSchema {
        class: declaring_pkg_name.to_string(),
        reason: format!("cannot resolve the owning package of imported {want_class} {type_name}") })?;
    let (owner_raw, _) = ctx.packages.get(&owner_pkg_name)
        .ok_or_else(|| ResolveError::MissingPackage(owner_pkg_name.clone()))?;
    let owner_names: Vec<String> = owner_raw.names.iter().map(|(n, _)| n.clone()).collect();
    let ti = find_typed_export(owner_raw, &owner_names, &type_name, want_class)
        .ok_or_else(|| ResolveError::MalformedSchema { class: declaring_pkg_name.to_string(),
            reason: format!("{want_class} {type_name} not found in package {owner_pkg_name}") })?;
    Ok((owner_pkg_name, ti))
}

/// Reads the LAST compact index between `[start, end)` (0 if none) -- an *Property export's type
/// tail is whatever compact(s) remain after the fixed header fields, and only the last one is the
/// real `type_ref` (an `ArrayProperty`'s extra leading compacts, out of this port's scope, are
/// skipped over the same way). Direct port of `_last_compact` (`uprops/base.py:76-80`).
fn last_compact(buf: &[u8], start: usize, end: usize) -> Result<i64, ResolveError> {
    let mut pos = start;
    let mut last = 0i64;
    while pos < end {
        let (v, next) = package_read::read_compact_index(buf, pos)
            .map_err(|e| ResolveError::MalformedPackage { name: "<property>".into(), reason: e.0 })?;
        last = v;
        pos = next;
    }
    Ok(last)
}

/// Decodes one `*Property` export's schema (name/kind/array_dim/category/type_ref). The leading
/// tagged-prop header goes through the full `read_property_tags` (the real `Engine.Actor.Touching`
/// exception, `ufield.py:32-35`), not a bare compact-index read. Direct port of `_decode_property`
/// (`ufield.py:14-61`), minus `enum_value_names`/`array_inner` (not needed by this task's own
/// tests; a later step adds them if it needs them).
fn decode_property_export(fqcn: &str, buf: &[u8], names: &[String], e: &package_read::ExportEntry,
    kind: &str, declaring_pkg: &str) -> Result<DecodedProp, ResolveError> {
    if e.ssize <= 0 {
        return Err(ResolveError::MalformedSchema {
            class: fqcn.to_string(),
            reason: format!("property {} has empty serial body (ssize={})",
                names.get(e.nm as usize).map(String::as_str).unwrap_or("?"), e.ssize),
        });
    }
    let so = e.soff as usize;
    let end = so + e.ssize as usize;
    let mk = |reason: String| ResolveError::MalformedPackage { name: "<property>".into(), reason };
    let (_tags, mut p) = package_read::read_property_tags(buf, so, end, names).map_err(|er| mk(er.0))?;
    let (_super, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let (_next_f, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let array_dim_raw = u32::from_le_bytes(
        buf.get(p..p + 4).ok_or_else(|| mk("truncated ArrayDim".into()))?.try_into().unwrap());
    p += 4;
    let array_dim = if array_dim_raw == 0 { 1 } else { array_dim_raw };
    let property_flags = u32::from_le_bytes(
        buf.get(p..p + 4).ok_or_else(|| mk("truncated PropertyFlags".into()))?.try_into().unwrap());
    p += 4;
    let (cat_idx, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let category = if cat_idx > 0 { names.get(cat_idx as usize).cloned() } else { None };
    if property_flags & CPF_NET != 0 {
        p += 2; // RepOffset
    }
    let type_ref = if KINDS_WITH_TYPE_REF.contains(&kind) { last_compact(buf, p, end)? } else { 0 };
    Ok(DecodedProp {
        name: names.get(e.nm as usize).cloned().unwrap_or_default(),
        kind: kind.to_string(),
        category,
        array_dim,
        type_ref,
        declaring_pkg: declaring_pkg.to_string(),
    })
}

/// A class's OWN (not inherited) properties: export records whose Outer is the class and whose
/// kind is a `*Property`. Direct port of `own_class_properties` (`uclass.py:24-34`).
fn own_class_properties(fqcn: &str, raw: &RawPackage, buf: &[u8], names: &[String],
    declaring_pkg: &str, class_idx0: usize) -> Result<Vec<DecodedProp>, ResolveError> {
    let class_idx1 = (class_idx0 + 1) as i32;
    let mut out = Vec::new();
    for e in &raw.exports {
        if e.outer == class_idx1 {
            if let Some(kind) = name_of_ref(raw, names, e.cls) {
                if PROPERTY_TYPES.contains(&kind.as_str()) {
                    out.push(decode_property_export(fqcn, buf, names, e, &kind, declaring_pkg)?);
                }
            }
        }
    }
    Ok(out)
}

/// A Struct export's `UStruct.Children` head ref: `[None][SuperField][Next][ScriptText][Children]`
/// (bare compacts, no tagged-prop header -- unlike a `*Property` export, `class_children_ref`'s own
/// UStruct body has no such exception). Direct port of `struct_children_ref` (`ufield.py:274-285`).
fn struct_children_ref(buf: &[u8], e: &package_read::ExportEntry) -> Result<i64, ResolveError> {
    let mk = |reason: String| ResolveError::MalformedPackage { name: "<struct>".into(), reason };
    let mut p = e.soff as usize;
    let (_none, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let (_sup, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let (_next_f, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let (_st, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let (children, _next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    Ok(children)
}

/// A UField export's `UField.Next` ref (the Children linked-list pointer) -- the header again goes
/// through the full `read_property_tags`, same Touching exception as `decode_property_export`.
/// Direct port of `_field_next` (`ufield.py:263-271`).
fn field_next(buf: &[u8], names: &[String], e: &package_read::ExportEntry) -> Result<i64, ResolveError> {
    let mk = |reason: String| ResolveError::MalformedPackage { name: "<struct member>".into(), reason };
    let so = e.soff as usize;
    let end = so + e.ssize.max(0) as usize;
    let (_tags, p) = package_read::read_property_tags(buf, so, end, names).map_err(|er| mk(er.0))?;
    let (_sup, p) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    let (next, _p) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    Ok(next)
}

/// A struct's OWN member list, walked via its `Children`/`Next` chain (declaration order) -- NOT
/// via outer-scan, and NOT including a super-struct's own members (that recursion is
/// `struct_members_with_super`'s own job, Step 5.6 -- every real caller in this file goes through
/// that wrapper, never this function directly, so a struct's FULL inherited shape is always used).
/// A non-property sibling in the chain is skipped but still followed via `Next`; a 256-iteration
/// cap guards a corrupt/cyclic chain. Reduced port of `struct_members` (`ufield.py:300-330`).
fn struct_own_members(fqcn: &str, raw: &RawPackage, buf: &[u8], names: &[String],
    declaring_pkg: &str, struct_idx0: usize) -> Result<Vec<DecodedProp>, ResolveError> {
    let e = raw.exports.get(struct_idx0).ok_or_else(|| ResolveError::MalformedSchema {
        class: fqcn.to_string(), reason: format!("struct export index {struct_idx0} out of range"),
    })?;
    let mut cur = struct_children_ref(buf, e)?;
    let mut out = Vec::new();
    for _ in 0..256 {
        if cur == 0 {
            return Ok(out);
        }
        if cur < 0 {
            return Err(ResolveError::MalformedSchema {
                class: fqcn.to_string(), reason: "struct child is an import".to_string(),
            });
        }
        let ee = raw.exports.get((cur - 1) as usize).ok_or_else(|| ResolveError::MalformedSchema {
            class: fqcn.to_string(), reason: format!("struct child export index {cur} out of range"),
        })?;
        if let Some(kind) = name_of_ref(raw, names, ee.cls) {
            if PROPERTY_TYPES.contains(&kind.as_str()) {
                out.push(decode_property_export(fqcn, buf, names, ee, &kind, declaring_pkg)?);
            }
        }
        cur = field_next(buf, names, ee)?;
    }
    Err(ResolveError::MalformedSchema {
        class: fqcn.to_string(), reason: "struct member chain did not terminate".to_string(),
    })
}

/// A struct's FULL member list: a LOCAL super-struct's own members (recursively, per THIS same
/// rule) prepended to its own Children-chain members -- Step 5.6's own recursion, direct port of
/// `struct_members`'s prepend-then-append shape (`ufield.py:300-330`). `seen` is the SAME
/// cycle-guard `struct_members` itself uses (a set of visited struct export indices, erroring on
/// revisit, `ufield.py:309-312`) -- a DIFFERENT mechanism from `struct_own_members`'s own
/// Children/Next 256-iteration cap, which still runs (unchanged) as this recursion's own base case.
/// An imported super-struct (`sup < 0`) is genuinely unsupported, matching the real Python's own
/// `SchemaError` there.
fn struct_members_with_super_rec(fqcn: &str, raw: &RawPackage, buf: &[u8], names: &[String],
    declaring_pkg: &str, struct_idx0: usize, seen: &mut std::collections::HashSet<usize>)
    -> Result<Vec<DecodedProp>, ResolveError> {
    if !seen.insert(struct_idx0) {
        return Err(ResolveError::MalformedSchema {
            class: fqcn.to_string(),
            reason: format!("cyclic super-struct reference at export {}", struct_idx0 + 1),
        });
    }
    let e = raw.exports.get(struct_idx0).ok_or_else(|| ResolveError::MalformedSchema {
        class: fqcn.to_string(), reason: format!("struct export index {struct_idx0} out of range"),
    })?;
    let mut out = Vec::new();
    if e.sup > 0 {
        out.extend(struct_members_with_super_rec(fqcn, raw, buf, names, declaring_pkg,
            (e.sup - 1) as usize, seen)?);
    } else if e.sup < 0 {
        return Err(ResolveError::MalformedSchema {
            class: fqcn.to_string(), reason: "imported super-struct not supported".to_string(),
        });
    }
    out.extend(struct_own_members(fqcn, raw, buf, names, declaring_pkg, struct_idx0)?);
    Ok(out)
}

/// `struct_members_with_super_rec` with a fresh cycle guard -- the entry point every OTHER
/// function in this file uses (never the `_rec` helper directly, and never plain
/// `struct_own_members` for a struct whose full inherited shape matters -- which is every real
/// caller: value decode, zero-fallback, and the `types` closure walk all need the FULL member list,
/// not just this struct's own Children chain).
fn struct_members_with_super(fqcn: &str, raw: &RawPackage, buf: &[u8], names: &[String],
    declaring_pkg: &str, struct_idx0: usize) -> Result<Vec<DecodedProp>, ResolveError> {
    let mut seen = std::collections::HashSet::new();
    struct_members_with_super_rec(fqcn, raw, buf, names, declaring_pkg, struct_idx0, &mut seen)
}

/// Decodes an ALREADY-RESOLVED Enum export's own bytes into ordered value names -- the inverse of
/// `add_enum_ex`'s fixture encoder. `idx1`/`raw`/`buf`/`names` are the OWNING package's own tables
/// (the caller, `resolved_enum_values` below, has already settled cross-package resolution via
/// `resolve_type_export` by the time this runs). Degrades to an empty `Vec` (not an error) if the
/// target export's own `cls` doesn't resolve to the literal `"Enum"` -- `enum_values`'s own
/// silent-degrade rule (`ufield.py:73`). Direct port of `enum_values` (`ufield.py:65-85`).
fn enum_values_at(raw: &RawPackage, buf: &[u8], names: &[String], idx1: i64)
    -> Result<Vec<String>, ResolveError> {
    let idx0 = (idx1 - 1) as usize;
    let Some(e) = raw.exports.get(idx0) else {
        return Ok(Vec::new());
    };
    if name_of_ref(raw, names, e.cls).as_deref() != Some("Enum") {
        return Ok(Vec::new());
    }
    let mk = |reason: String| ResolveError::MalformedPackage { name: "<enum>".into(), reason };
    let mut p = e.soff as usize;
    let (_none, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let (_next_f, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let (_skip, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let (count, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
    p = next;
    let mut vals = Vec::new();
    for _ in 0..count {
        let (v, next) = package_read::read_compact_index(buf, p).map_err(|er| mk(er.0))?;
        p = next;
        let name = names.get(v as usize).cloned()
            .ok_or_else(|| mk(format!("enum value name index {v} out of range")))?;
        vals.push(name);
    }
    let end = (e.soff + e.ssize) as usize;
    if p != end {
        return Err(mk(format!("enum body did not consume to EOF (cursor {p} != {end})")));
    }
    Ok(vals)
}

/// A `*Property`'s enum value names, resolving `type_ref` cross-package first (Step 5.7's
/// `resolve_type_export`) -- a POSITIVE `type_ref` is a local index, a NEGATIVE one is an import,
/// both resolved here; only `type_ref == 0` (no enum reference at all) degrades to `[]`, matching
/// every call site's own kind-guard, kept here too so this function is safe to call unguarded.
/// `declaring_pkg` is the property's OWN declaring package (`_pkg_for_owner`'s rule -- not
/// necessarily the leaf class's own package).
fn resolved_enum_values(ctx: &ResolutionContext, declaring_pkg: &str, type_ref: i64)
    -> Result<Vec<String>, ResolveError> {
    if type_ref == 0 {
        return Ok(Vec::new());
    }
    let (owner_pkg, ti) = resolve_type_export(ctx, declaring_pkg, type_ref, "Enum")?;
    let (owner_raw, owner_buf) = ctx.packages.get(&owner_pkg)
        .ok_or_else(|| ResolveError::MissingPackage(owner_pkg.clone()))?;
    let owner_names: Vec<String> = owner_raw.names.iter().map(|(n, _)| n.clone()).collect();
    enum_values_at(owner_raw, owner_buf, &owner_names, ti)
}

/// Spec §1's `(package, outer, name)` identity key for a struct/enum export at 1-based index
/// `idx1` in `pkg_name`'s own tables: `<package>.<outer name>.<bare name>` when the export's own
/// `outer` field resolves (via `name_of_ref`) to a real container OTHER than the literal `"Object"`
/// (the universal root class, never a meaningful container for this purpose); `<package>.<bare
/// name>` otherwise (outer absent, or resolving to `Object`). Direct port of the parent spec's own
/// identity rule (Step 5) -- e.g. `Core.Scale.ESheerAxis`'s `Scale` component comes from
/// `ESheerAxis`'s own `outer` pointing at the `Scale` struct's export, not from any import.
fn type_identity_key(raw: &RawPackage, names: &[String], pkg_name: &str, idx1: i64)
    -> Result<String, ResolveError> {
    let e = raw.exports.get((idx1 - 1) as usize).ok_or_else(|| ResolveError::MalformedSchema {
        class: pkg_name.to_string(), reason: format!("type ref {idx1} out of range"),
    })?;
    let bare_name = names.get(e.nm as usize).cloned().ok_or_else(|| ResolveError::MalformedSchema {
        class: pkg_name.to_string(), reason: format!("type export {idx1} name index out of range"),
    })?;
    match name_of_ref(raw, names, e.outer as i64) {
        Some(outer) if outer != "Object" => Ok(format!("{pkg_name}.{outer}.{bare_name}")),
        _ => Ok(format!("{pkg_name}.{bare_name}")),
    }
}

/// CLI_STYLE's own `format_float` (`uprops/values.py:84-90`) -- the display form this whole port
/// targets (floats trimmed: `24`, `0.5`; never `T3D_STYLE`'s always-six-decimals form). Cast to
/// `i64` before `.to_string()` in the integral branch, NOT `v.trunc().to_string()` on the raw
/// float: `(-0.0f64).trunc().to_string()` renders `"-0"` (Rust preserves the float sign bit through
/// `Display`), while Python's `str(int(-0.0))` gives `"0"` (`int()` normalizes the sign away).
fn format_float(v: f64) -> String {
    if v == v.trunc() && v.abs() < 1e15 {
        (v.trunc() as i64).to_string()
    } else {
        format!("{v:.6}").trim_end_matches('0').trim_end_matches('.').to_string()
    }
}

/// Step 4.5's own SEPARATE, hardcoded `TYPED_FIELDS` fallback constants (`effective_props.py:144,
/// 163,172,175-176` / `transform.DEFAULT_SHEER_AXIS`) -- NOT derived from `zero_default` below.
/// Reached only when a `TYPED_FIELDS` leaf (Location/MainScale/PostScale) has no class default
/// anywhere in its Super chain -- wired in by `typed_field_fallback_tree` (Step 8).
fn typed_field_fallback(field: &str) -> &'static str {
    match field {
        "Location.X" | "Location.Y" | "Location.Z" => "0",
        "Scale.X" | "Scale.Y" | "Scale.Z" => "1",
        "SheerRate" => "0",
        "SheerAxis" => "SHEER_ZX",
        other => panic!("typed_field_fallback: unknown field {other}"),
    }
}

/// One struct default's decoded VALUE: `RenderedDefault::Text` for every scalar/enum ptype,
/// `RenderedDefault::Tree` for `PT_STRUCT` (Step 4.6's own tree shape, not a joined string).
enum RenderedDefault {
    Text(String),
    Tree(DefaultValue),
}

/// Decodes one struct value's binary block (`raw[start..]`) against `members` (declaration order,
/// already resolved -- the FULL super-chain-recursive list `struct_members_with_super` produces).
/// Step 4.6's own tree-assembly rule: an included scalar member keys under its bare
/// name to `DefaultValue::Scalar`; a member with `array_dim > 1` keys under its bare name (ONE key)
/// to `DefaultValue::Array` (one entry per element); a nested struct member keys to a recursive
/// `DefaultValue::Struct`; an EXCLUDED-kind member (`EXCLUDED_STRUCT_MEMBER_KINDS`) is omitted from
/// the map but its bytes are still consumed. Reduced-port sibling of `_decode_struct_bin_at`
/// (`uprops/values.py:142-203`) targeting this tree shape instead of `(name, text)` pairs.
fn decode_struct_members_bin(fqcn: &str, ctx: &ResolutionContext, value_pkg: &str,
    members: &[DecodedProp], raw: &[u8], start: usize)
    -> Result<(BTreeMap<String, DefaultValue>, usize), ResolveError> {
    let mut out = BTreeMap::new();
    let mut p = start;
    for m in members {
        let excluded = EXCLUDED_STRUCT_MEMBER_KINDS.contains(&m.kind.as_str());
        if m.array_dim > 1 {
            let mut elems = Vec::with_capacity(m.array_dim as usize);
            for _ in 0..m.array_dim {
                let (v, next) = decode_one_member_value(fqcn, ctx, value_pkg, m, raw, p)?;
                p = next;
                elems.push(v);
            }
            if !excluded {
                out.insert(m.name.clone(), DefaultValue::Array(elems));
            }
        } else {
            let (v, next) = decode_one_member_value(fqcn, ctx, value_pkg, m, raw, p)?;
            p = next;
            if !excluded {
                out.insert(m.name.clone(), v);
            }
        }
    }
    Ok((out, p))
}

/// One struct member ELEMENT's binary value -> its `DefaultValue`. Direct per-kind port of
/// `_decode_struct_bin_at`'s own dispatch (`uprops/values.py:163-202`), CLI_STYLE (a struct-member
/// `ByteProperty` is ALWAYS its plain number here -- `_byte_member_text` only renders an enum NAME
/// under `T3D_STYLE`, which this port never uses). `ArrayProperty`/`PointerProperty` (or any other
/// kind outside this dispatch) have no defined struct-member wire form and are a hard decode error,
/// matching Python's own `raise SchemaError` for an unsupported struct member kind.
fn decode_one_member_value(fqcn: &str, ctx: &ResolutionContext, value_pkg: &str,
    m: &DecodedProp, raw: &[u8], p: usize) -> Result<(DefaultValue, usize), ResolveError> {
    let mk = |reason: String| ResolveError::MalformedSchema { class: fqcn.to_string(), reason };
    match m.kind.as_str() {
        "IntProperty" => {
            let chunk = raw.get(p..p + 4)
                .ok_or_else(|| mk(format!("struct value truncated at member {}", m.name)))?;
            Ok((DefaultValue::Scalar(i32::from_le_bytes(chunk.try_into().unwrap()).to_string()), p + 4))
        }
        "FloatProperty" => {
            let chunk = raw.get(p..p + 4)
                .ok_or_else(|| mk(format!("struct value truncated at member {}", m.name)))?;
            let f = f32::from_le_bytes(chunk.try_into().unwrap()) as f64;
            Ok((DefaultValue::Scalar(format_float(f)), p + 4))
        }
        "ByteProperty" => {
            let b = *raw.get(p).ok_or_else(|| mk(format!("struct value truncated at member {}", m.name)))?;
            Ok((DefaultValue::Scalar(b.to_string()), p + 1))
        }
        "BoolProperty" => {
            let b = *raw.get(p).ok_or_else(|| mk(format!("struct value truncated at member {}", m.name)))?;
            Ok((DefaultValue::Scalar(if b != 0 { "True" } else { "False" }.to_string()), p + 1))
        }
        "NameProperty" => {
            let (ni, next) = package_read::read_compact_index(raw, p)
                .map_err(|e| ResolveError::MalformedPackage { name: "<struct value>".into(), reason: e.0 })?;
            let (value_raw, _buf) = ctx.packages.get(value_pkg)
                .ok_or_else(|| ResolveError::MissingPackage(value_pkg.to_string()))?;
            let text = if ni >= 0 { value_raw.names.get(ni as usize).map(|(n, _)| n.clone()) } else { None };
            Ok((DefaultValue::Scalar(text.unwrap_or_else(|| "None".to_string())), next))
        }
        "StrProperty" => {
            let (s, next) = package_read::read_fstring(raw, p)
                .map_err(|e| ResolveError::MalformedPackage { name: "<struct value>".into(), reason: e.0 })?;
            Ok((DefaultValue::Scalar(s), next))
        }
        "ObjectProperty" | "ClassProperty" => {
            let (_v, next) = package_read::read_compact_index(raw, p)
                .map_err(|e| ResolveError::MalformedPackage { name: "<struct value>".into(), reason: e.0 })?;
            Ok((DefaultValue::Scalar(String::new()), next)) // excluded -- caller omits this from the map
        }
        "StructProperty" => {
            let (owner_pkg, ti) = resolve_type_export(ctx, &m.declaring_pkg, m.type_ref, "Struct")?;
            let (owner_raw, owner_buf) = ctx.packages.get(&owner_pkg)
                .ok_or_else(|| ResolveError::MissingPackage(owner_pkg.clone()))?;
            let owner_names: Vec<String> = owner_raw.names.iter().map(|(n, _)| n.clone()).collect();
            let sub_members = struct_members_with_super(fqcn, owner_raw, owner_buf, &owner_names,
                &owner_pkg, (ti - 1) as usize)?;
            let (sub_tree, next) = decode_struct_members_bin(fqcn, ctx, value_pkg, &sub_members, raw, p)?;
            Ok((DefaultValue::Struct(sub_tree), next))
        }
        other => Err(mk(format!("unsupported struct member kind {other} ({})", m.name))),
    }
}

/// A `StructProperty` default TAG's own value -> the Step 4.6 tree, resolving `prop`'s struct type
/// LOCALLY (`prop.type_ref`, a positive index into `prop.declaring_pkg`) and consuming exactly the
/// tag's own raw bytes (a leftover or short read is `MalformedSchema`, matching
/// `struct_tag_member_tree`'s own exact-consume check).
fn decode_struct_tag_tree(fqcn: &str, ctx: &ResolutionContext, value_pkg: &str, prop: &DecodedProp,
    raw_value: &[u8]) -> Result<DefaultValue, ResolveError> {
    let (owner_pkg, ti) = resolve_type_export(ctx, &prop.declaring_pkg, prop.type_ref, "Struct")?;
    let (owner_raw, owner_buf) = ctx.packages.get(&owner_pkg)
        .ok_or_else(|| ResolveError::MissingPackage(owner_pkg.clone()))?;
    let owner_names: Vec<String> = owner_raw.names.iter().map(|(n, _)| n.clone()).collect();
    let members = struct_members_with_super(fqcn, owner_raw, owner_buf, &owner_names, &owner_pkg,
        (ti - 1) as usize)?;
    let (tree, pos) = decode_struct_members_bin(fqcn, ctx, value_pkg, &members, raw_value, 0)?;
    if pos != raw_value.len() {
        return Err(ResolveError::MalformedSchema {
            class: fqcn.to_string(),
            reason: format!("struct value did not consume exactly ({pos} != {})", raw_value.len()),
        });
    }
    Ok(DefaultValue::Struct(tree))
}

/// One defaults `RawPropertyTag` -> its rendered value (Step 4's own per-tag VALUE dispatch,
/// `render_default_tag`, `uprops/values.py:425-468`). Renders EVERY tag schema-agnostically --
/// called even for a tag whose matching `prop` is `None` or excluded from the wire shape -- so an
/// unsupported `ptype` (e.g. `PT_ARRAY=9`) always surfaces as an error here, matching
/// `resolve_class_defaults`'s real behavior exactly (round 12/13's review). `tag_pkg` is the
/// package the tag was SERIALIZED in (its own object/name compacts resolve there); `prop`'s own
/// struct/enum type resolves against ITS declaring package instead (`_pkg_for_owner`, Step 5.7),
/// cross-package aware via `resolve_type_export`/`resolved_enum_values`.
fn render_default_tag(fqcn: &str, ctx: &ResolutionContext, tag_pkg: &str,
    tag: &package_read::RawPropertyTag, prop: Option<&DecodedProp>)
    -> Result<RenderedDefault, ResolveError> {
    const PT_BYTE: u8 = 1;
    const PT_INT: u8 = 2;
    const PT_BOOL: u8 = 3;
    const PT_FLOAT: u8 = 4;
    const PT_OBJECT: u8 = 5;
    const PT_NAME: u8 = 6;
    const PT_STR_LEGACY: u8 = 7;
    const PT_STRUCT: u8 = 10;
    const PT_STR: u8 = 13;
    let mk = |reason: String| ResolveError::MalformedSchema { class: fqcn.to_string(), reason };
    match tag.ptype {
        PT_BOOL => Ok(RenderedDefault::Text(
            if tag.bool_value.unwrap_or(false) { "True" } else { "False" }.to_string())),
        PT_BYTE => {
            let v = *tag.raw.first().ok_or_else(|| mk(format!("truncated byte default for {}", tag.name)))?;
            if let Some(p) = prop {
                if p.kind == "ByteProperty" && p.type_ref != 0 {
                    let enum_names = resolved_enum_values(ctx, &p.declaring_pkg, p.type_ref)?;
                    if let Some(name) = enum_names.get(v as usize) {
                        return Ok(RenderedDefault::Text(name.clone()));
                    }
                }
            }
            Ok(RenderedDefault::Text(v.to_string()))
        }
        PT_INT => {
            let arr: [u8; 4] = tag.raw.as_slice().try_into()
                .map_err(|_| mk(format!("malformed int default for {}", tag.name)))?;
            Ok(RenderedDefault::Text(i32::from_le_bytes(arr).to_string()))
        }
        PT_FLOAT => {
            let arr: [u8; 4] = tag.raw.as_slice().try_into()
                .map_err(|_| mk(format!("malformed float default for {}", tag.name)))?;
            Ok(RenderedDefault::Text(format_float(f32::from_le_bytes(arr) as f64)))
        }
        PT_OBJECT => {
            // A plain compact-index read, no name/path resolution -- Object is always an excluded
            // kind (no ResolvedProp variant ever surfaces this text), but the tag must still decode
            // without erroring (round 13's review).
            package_read::read_compact_index(&tag.raw, 0)
                .map_err(|e| ResolveError::MalformedPackage { name: "<default>".into(), reason: e.0 })?;
            Ok(RenderedDefault::Text(String::new()))
        }
        PT_NAME => {
            let (ni, _) = package_read::read_compact_index(&tag.raw, 0)
                .map_err(|e| ResolveError::MalformedPackage { name: "<default>".into(), reason: e.0 })?;
            let (raw, _buf) = ctx.packages.get(tag_pkg)
                .ok_or_else(|| ResolveError::MissingPackage(tag_pkg.to_string()))?;
            let text = if ni >= 0 { raw.names.get(ni as usize).map(|(n, _)| n.clone()) } else { None };
            Ok(RenderedDefault::Text(text.unwrap_or_else(|| "None".to_string())))
        }
        PT_STR | PT_STR_LEGACY => {
            let s = if tag.ptype == PT_STR {
                package_read::read_fstring(&tag.raw, 0)
                    .map_err(|e| ResolveError::MalformedPackage { name: "<default>".into(), reason: e.0 })?.0
            } else {
                let cut = tag.raw.iter().position(|&b| b == 0).unwrap_or(tag.raw.len());
                tag.raw[..cut].iter().map(|&b| b as char).collect()
            };
            Ok(RenderedDefault::Text(s))
        }
        PT_STRUCT => {
            let prop = prop.ok_or_else(||
                mk(format!("cannot render struct default {} without its schema", tag.name)))?;
            Ok(RenderedDefault::Tree(decode_struct_tag_tree(fqcn, ctx, tag_pkg, prop, &tag.raw)?))
        }
        other => Err(mk(format!("unsupported default value type {other} for {}", tag.name))),
    }
}

/// Step 4.5's own generic zero-value fallback ladder (`propedit/structtext.py:47-70`'s
/// `zero_value`, ported to this port's TREE-shaped `Struct` default rather than a flat string).
/// Per-kind, NOT a uniform "0"/empty string: `BoolProperty` -> `"False"`; `IntProperty`/
/// `FloatProperty` -> `"0"`; `ByteProperty` -> the enum's own FIRST value name if it has a LOCAL
/// enum, else `"0"`; `NameProperty`/`ObjectProperty`/`ClassProperty` -> `"None"`; `StrProperty` ->
/// `""`; `StructProperty` -> recurse per member (a member static array repeats the SAME zero value
/// across every element); anything else (Array/Pointer) -> `""`, matching Python's own catch-all.
/// The struct recursion adds a filter Python's own `zero_value` lacks: a member computes its zero
/// value regardless of kind (so an excluded member's presence in the shape doesn't break the walk)
/// but is OMITTED from the assembled map when its kind is in `EXCLUDED_STRUCT_MEMBER_KINDS` -- the
/// same key-omission rule `decode_struct_members_bin` uses for a real (non-zero) default, so a
/// struct's zero-fallback and its real-default path never disagree on which keys appear.
fn zero_default(fqcn: &str, ctx: &ResolutionContext, prop: &DecodedProp)
    -> Result<DefaultValue, ResolveError> {
    match prop.kind.as_str() {
        "BoolProperty" => Ok(DefaultValue::Scalar("False".to_string())),
        "IntProperty" | "FloatProperty" => Ok(DefaultValue::Scalar("0".to_string())),
        "ByteProperty" => {
            let enum_names = resolved_enum_values(ctx, &prop.declaring_pkg, prop.type_ref)?;
            if let Some(first) = enum_names.first() {
                return Ok(DefaultValue::Scalar(first.clone()));
            }
            Ok(DefaultValue::Scalar("0".to_string()))
        }
        "NameProperty" | "ObjectProperty" | "ClassProperty" => Ok(DefaultValue::Scalar("None".to_string())),
        "StrProperty" => Ok(DefaultValue::Scalar(String::new())),
        "StructProperty" => {
            let (owner_pkg, ti) = resolve_type_export(ctx, &prop.declaring_pkg, prop.type_ref, "Struct")?;
            let (raw, buf) = ctx.packages.get(&owner_pkg)
                .ok_or_else(|| ResolveError::MissingPackage(owner_pkg.clone()))?;
            let names: Vec<String> = raw.names.iter().map(|(n, _)| n.clone()).collect();
            let members = struct_members_with_super(fqcn, raw, buf, &names, &owner_pkg, (ti - 1) as usize)?;
            let mut out = BTreeMap::new();
            for m in &members {
                let excluded = EXCLUDED_STRUCT_MEMBER_KINDS.contains(&m.kind.as_str());
                let z = zero_default(fqcn, ctx, m)?;
                if m.array_dim > 1 {
                    if !excluded {
                        out.insert(m.name.clone(), DefaultValue::Array(vec![z; m.array_dim as usize]));
                    }
                } else if !excluded {
                    out.insert(m.name.clone(), z);
                }
            }
            Ok(DefaultValue::Struct(out))
        }
        _ => Ok(DefaultValue::Scalar(String::new())), // Array/Pointer: out of scope, matches zero_value's own catch-all
    }
}

/// `zero_default` for a prop whose ResolvedProp is Scalar/Enum (never Struct) -- unwraps the
/// `DefaultValue::Scalar` text `zero_default` always returns for these kinds.
fn scalar_zero_text(fqcn: &str, ctx: &ResolutionContext, prop: &DecodedProp) -> Result<String, ResolveError> {
    match zero_default(fqcn, ctx, prop)? {
        DefaultValue::Scalar(s) => Ok(s),
        _ => unreachable!("zero_default returned a non-scalar for a scalar/enum-kind prop"),
    }
}

/// Resolves `prop`'s struct/enum `type_ref` cross-package (Step 5.7's `resolve_type_export`), keys
/// the target via Step 5's identity rule, and inserts its own closure into `types_out` if not
/// already present (Step 5.5) -- returns the identity key, ready for `struct_type`/`enum_type`.
/// `want_class` is `"Struct"` or `"Enum"`; never called for Object/Class/Array kinds (see
/// `resolve_type_export`'s own doc for why) -- structurally true here, since neither `render_prop`
/// nor `member_type_shape` ever calls it for those. `in_progress` is `collect_struct_type`'s own
/// member-cycle guard (irrelevant to the Enum branch, which never recurses) -- see that function's
/// doc.
fn resolve_and_collect_type(fqcn: &str, ctx: &ResolutionContext, prop: &DecodedProp,
    want_class: &str, types_out: &mut BTreeMap<String, TypeShape>,
    in_progress: &mut std::collections::BTreeSet<String>) -> Result<String, ResolveError> {
    let (owner_pkg, ti) = resolve_type_export(ctx, &prop.declaring_pkg, prop.type_ref, want_class)?;
    if want_class == "Enum" {
        collect_enum_type(ctx, &owner_pkg, ti, types_out)
    } else {
        collect_struct_type(fqcn, ctx, &owner_pkg, ti, types_out, in_progress)
    }
}

/// Inserts `owner_pkg`'s Enum export `ti` into `types_out` (keyed by Step 5's identity rule) if not
/// already present, and returns that key. Idempotent -- a repeat reference to the same enum is a
/// cheap lookup, not a re-decode.
fn collect_enum_type(ctx: &ResolutionContext, owner_pkg: &str, ti: i64,
    types_out: &mut BTreeMap<String, TypeShape>) -> Result<String, ResolveError> {
    let (raw, buf) = ctx.packages.get(owner_pkg)
        .ok_or_else(|| ResolveError::MissingPackage(owner_pkg.to_string()))?;
    let names: Vec<String> = raw.names.iter().map(|(n, _)| n.clone()).collect();
    let key = type_identity_key(raw, &names, owner_pkg, ti)?;
    if !types_out.contains_key(&key) {
        let values = enum_values_at(raw, buf, &names, ti)?;
        types_out.insert(key.clone(), TypeShape::Enum { values });
    }
    Ok(key)
}

/// Inserts `owner_pkg`'s Struct export `ti` into `types_out` (keyed by Step 5's identity rule) if
/// not already present, recursing into every OWN member's own struct/enum type first (Step 5.5's
/// transitive closure) -- by the time this returns, `types_out` holds this struct's WHOLE
/// transitive reference set, not just its direct members. Member list is the FULL super-chain-
/// recursive one (Step 5.6's `struct_members_with_super`), so an inherited member's own struct/enum
/// type is collected too.
///
/// `in_progress` guards a struct that references itself through a MEMBER (directly, or via a cycle
/// of struct-typed members: A has a member of type B, B has a member of type A) -- a DIFFERENT
/// cycle from the SUPER-chain one Step 5.6's `seen` already guards, and this closure walk's own
/// analogue of it: insert this struct's own key BEFORE recursing into its members, and error on a
/// repeat rather than recursing further, exactly mirroring `struct_members_with_super_rec`'s
/// pattern (insert-then-recurse, error on re-insert). Unlike the SUPER chain (`sup < 0` is a hard
/// parse-time error, so only a genuinely cyclic `sup` chain can loop), a member-typed cycle is
/// reachable from ordinary, individually-valid schema shapes -- two structs each declaring a
/// `StructProperty` member of the other -- so this is a real, not just theoretical, malformed/fuzzed-
/// package hazard, the same threat model the Children/Next 256-iteration cap and the `sup`-chain
/// `seen`-set both already exist for in this file. A key already FINISHED (present in `types_out`)
/// short-circuits before this check -- that is normal, non-cyclic re-reference (e.g. two sibling
/// props of the same struct type), not a cycle.
fn collect_struct_type(fqcn: &str, ctx: &ResolutionContext, owner_pkg: &str, ti: i64,
    types_out: &mut BTreeMap<String, TypeShape>, in_progress: &mut std::collections::BTreeSet<String>)
    -> Result<String, ResolveError> {
    let (raw, buf) = ctx.packages.get(owner_pkg)
        .ok_or_else(|| ResolveError::MissingPackage(owner_pkg.to_string()))?;
    let names: Vec<String> = raw.names.iter().map(|(n, _)| n.clone()).collect();
    let key = type_identity_key(raw, &names, owner_pkg, ti)?;
    if types_out.contains_key(&key) {
        return Ok(key);
    }
    if !in_progress.insert(key.clone()) {
        return Err(ResolveError::MalformedSchema {
            class: fqcn.to_string(),
            reason: format!("cyclic struct member reference at {key}"),
        });
    }
    let members = struct_members_with_super(fqcn, raw, buf, &names, owner_pkg, (ti - 1) as usize)?;
    let mut type_members = Vec::new();
    for m in &members {
        if let Some(tm) = member_type_shape(fqcn, ctx, m, types_out, in_progress)? {
            type_members.push(tm);
        }
    }
    types_out.insert(key.clone(), TypeShape::Struct { members: type_members });
    Ok(key)
}

/// One struct member's own `TypeMember` (Step 5.5), recursing into `resolve_and_collect_type` for
/// a struct/enum-typed member so its own type lands in `types_out` too (the transitive closure).
/// `None` for an excluded kind (`EXCLUDED_STRUCT_MEMBER_KINDS`) -- omitted from
/// `TypeShape::Struct.members` the same way it's omitted from a decoded default value's map (no
/// `MemberKind` variant could represent it anyway). Any OTHER kind with no defined struct-member
/// wire form (`ArrayProperty`/`PointerProperty`) errors, matching `decode_one_member_value`'s own
/// dispatch -- this port's own test corpus has no such member, so this arm is untested but not
/// fictional (a real one would already fail struct VALUE decode the same way). `in_progress` is
/// threaded straight through to `resolve_and_collect_type`/`collect_struct_type` -- see that
/// function's own doc for the member-cycle guard it implements.
fn member_type_shape(fqcn: &str, ctx: &ResolutionContext, m: &DecodedProp,
    types_out: &mut BTreeMap<String, TypeShape>, in_progress: &mut std::collections::BTreeSet<String>)
    -> Result<Option<TypeMember>, ResolveError> {
    if EXCLUDED_STRUCT_MEMBER_KINDS.contains(&m.kind.as_str()) {
        return Ok(None);
    }
    let scalar_kind = match m.kind.as_str() {
        "IntProperty" => Some(ScalarKind::Int),
        "FloatProperty" => Some(ScalarKind::Float),
        "BoolProperty" => Some(ScalarKind::Bool),
        "NameProperty" => Some(ScalarKind::Name),
        "StrProperty" => Some(ScalarKind::StringKind),
        "ByteProperty" if m.type_ref == 0 => Some(ScalarKind::Byte),
        _ => None,
    };
    if let Some(sk) = scalar_kind {
        let kind = if m.array_dim > 1 { MemberKind::ScalarArray { array_dim: m.array_dim, kind: sk } }
                   else { MemberKind::Scalar(sk) };
        return Ok(Some(TypeMember { name: m.name.clone(), kind }));
    }
    match m.kind.as_str() {
        "ByteProperty" => {
            let key = resolve_and_collect_type(fqcn, ctx, m, "Enum", types_out, in_progress)?;
            let kind = if m.array_dim > 1 { MemberKind::EnumArray { array_dim: m.array_dim, enum_type: key } }
                       else { MemberKind::Enum { enum_type: key } };
            Ok(Some(TypeMember { name: m.name.clone(), kind }))
        }
        "StructProperty" => {
            let key = resolve_and_collect_type(fqcn, ctx, m, "Struct", types_out, in_progress)?;
            let kind = if m.array_dim > 1 { MemberKind::StructArray { array_dim: m.array_dim, struct_type: key } }
                       else { MemberKind::Struct { struct_type: key } };
            Ok(Some(TypeMember { name: m.name.clone(), kind }))
        }
        other => Err(ResolveError::MalformedSchema {
            class: fqcn.to_string(), reason: format!("unsupported struct member kind {other} ({})", m.name),
        }),
    }
}

/// `_canonical_path`'s own dotted spelling for one path-segment addition (`effective_props.py:358-
/// 369`): a literal array index joins with a plain `.`, e.g. `AlliancesEx.2` -- NEVER `[2]`/`(2)`.
/// This task never builds a full multi-level path (that's `resolve_actor_props`'s own job, Task 5),
/// but Step 11's array-element decode below is the first place THIS function needs to name which
/// index broke, so it must already use the convention Task 5 builds on, not invent a different one.
fn indexed_path(base: &str, index: i64) -> String {
    format!("{base}.{index}")
}

/// Re-labels a per-array-element decode failure with its own index, using `indexed_path`'s dotted
/// convention, before it bubbles up to the caller's own top-level-member wrap (Step 6.5) -- so the
/// final message names BOTH the top-level prop and which element broke (e.g. `member AlliancesEx:
/// AlliancesEx.2: ...`), never just the top-level name for an array. Non-`MalformedSchema` errors
/// (`MissingPackage` etc.) pass through unchanged -- those already name the real offender (a
/// package), and re-labelling would only obscure it.
fn reindex_element_error(e: ResolveError, base: &str, index: i64) -> ResolveError {
    match e {
        ResolveError::MalformedSchema { class, reason } => ResolveError::MalformedSchema {
            class, reason: format!("{}: {reason}", indexed_path(base, index)),
        },
        other => other,
    }
}

/// One merged `DecodedProp` -> its `ResolvedProp`, using `default_values` (keyed
/// `(name.casefold(), array_index)`) or the Step 4.5 zero fallback per-index when absent. `None`
/// for a kind with no wire representation at all (`ObjectProperty`/`ClassProperty`/`ArrayProperty`/
/// `PointerProperty`) -- structural, not Step 6's own name-based `HARD_REJECT`/`TYPED_FIELDS`
/// exclusion: there is simply no `ResolvedProp` variant these kinds could ever produce. `types_out`
/// is Step 5.5's own closure accumulator -- a struct/enum-carrying prop inserts its own type (and,
/// for a struct, its transitive closure) via `resolve_and_collect_type`.
///
/// `array_dim > 1` (Step 11): builds a `ResolvedProp::Array` instead of a scalar/enum/struct leaf,
/// one `DefaultValue` per index, POSITIONALLY -- `array_dim` entries always, several identical
/// values never collapsed, a sparse default block (fewer stated indices than `array_dim`) filling
/// every un-stated index with the SAME per-kind zero rule a whole unstated scalar prop would use.
fn render_prop(fqcn: &str, ctx: &ResolutionContext, prop: &DecodedProp,
    default_values: &BTreeMap<(String, i64), RenderedDefault>,
    types_out: &mut BTreeMap<String, TypeShape>,
    in_progress: &mut std::collections::BTreeSet<String>) -> Result<Option<ResolvedProp>, ResolveError> {
    let category = prop.category.clone().unwrap_or_else(|| "Uncategorized".to_string());
    let name_lower = prop.name.to_lowercase();
    let shape_mismatch = |what: &str| ResolveError::MalformedSchema {
        class: fqcn.to_string(), reason: format!("{}: {what}", prop.name),
    };

    // One element's scalar TEXT (never a Tree) -- shared by every non-struct kind, single and
    // array alike; `i` is the array index for an array element, 0 for a non-array prop.
    let scalar_text_at = |i: i64, what: &str| -> Result<String, ResolveError> {
        match default_values.get(&(name_lower.clone(), i)) {
            Some(RenderedDefault::Text(t)) => Ok(t.clone()),
            Some(RenderedDefault::Tree(_)) =>
                Err(shape_mismatch(&format!("struct-shaped default for a {what} prop"))),
            None => scalar_zero_text(fqcn, ctx, prop),
        }
    };
    // One element's struct TREE (never scalar text).
    let struct_tree_at = |i: i64| -> Result<DefaultValue, ResolveError> {
        match default_values.get(&(name_lower.clone(), i)) {
            Some(RenderedDefault::Tree(t)) => Ok(t.clone()),
            Some(RenderedDefault::Text(_)) => Err(shape_mismatch("scalar-shaped default for a struct prop")),
            None => zero_default(fqcn, ctx, prop),
        }
    };

    match prop.kind.as_str() {
        "IntProperty" | "FloatProperty" | "BoolProperty" | "NameProperty" | "StrProperty" => {
            let kind = match prop.kind.as_str() {
                "IntProperty" => ScalarKind::Int,
                "FloatProperty" => ScalarKind::Float,
                "BoolProperty" => ScalarKind::Bool,
                "NameProperty" => ScalarKind::Name,
                _ => ScalarKind::StringKind,
            };
            if prop.array_dim > 1 {
                let mut vals = Vec::with_capacity(prop.array_dim as usize);
                for i in 0..prop.array_dim as i64 {
                    vals.push(DefaultValue::Scalar(scalar_text_at(i, "scalar")
                        .map_err(|e| reindex_element_error(e, &prop.name, i))?));
                }
                return Ok(Some(ResolvedProp::Array { name: prop.name.clone(), category,
                    array_dim: prop.array_dim, element: ArrayElementKind::Scalar(kind), default_value: vals }));
            }
            let default_value = scalar_text_at(0, "scalar")?;
            Ok(Some(ResolvedProp::Scalar { name: prop.name.clone(), category, kind, default_value }))
        }
        "ByteProperty" if prop.type_ref != 0 => {
            let enum_type = resolve_and_collect_type(fqcn, ctx, prop, "Enum", types_out, in_progress)?;
            if prop.array_dim > 1 {
                let mut vals = Vec::with_capacity(prop.array_dim as usize);
                for i in 0..prop.array_dim as i64 {
                    vals.push(DefaultValue::Scalar(scalar_text_at(i, "enum")
                        .map_err(|e| reindex_element_error(e, &prop.name, i))?));
                }
                return Ok(Some(ResolvedProp::Array { name: prop.name.clone(), category,
                    array_dim: prop.array_dim, element: ArrayElementKind::Enum(enum_type), default_value: vals }));
            }
            let default_value = scalar_text_at(0, "enum")?;
            Ok(Some(ResolvedProp::Enum { name: prop.name.clone(), category, enum_type, default_value }))
        }
        "ByteProperty" => {
            if prop.array_dim > 1 {
                let mut vals = Vec::with_capacity(prop.array_dim as usize);
                for i in 0..prop.array_dim as i64 {
                    vals.push(DefaultValue::Scalar(scalar_text_at(i, "byte")
                        .map_err(|e| reindex_element_error(e, &prop.name, i))?));
                }
                return Ok(Some(ResolvedProp::Array { name: prop.name.clone(), category,
                    array_dim: prop.array_dim, element: ArrayElementKind::Scalar(ScalarKind::Byte),
                    default_value: vals }));
            }
            let default_value = scalar_text_at(0, "byte")?;
            Ok(Some(ResolvedProp::Scalar { name: prop.name.clone(), category, kind: ScalarKind::Byte, default_value }))
        }
        "StructProperty" => {
            let struct_type = resolve_and_collect_type(fqcn, ctx, prop, "Struct", types_out, in_progress)?;
            if prop.array_dim > 1 {
                let mut vals = Vec::with_capacity(prop.array_dim as usize);
                for i in 0..prop.array_dim as i64 {
                    vals.push(struct_tree_at(i).map_err(|e| reindex_element_error(e, &prop.name, i))?);
                }
                return Ok(Some(ResolvedProp::Array { name: prop.name.clone(), category,
                    array_dim: prop.array_dim, element: ArrayElementKind::Struct(struct_type),
                    default_value: vals }));
            }
            let default_value = struct_tree_at(0)?;
            Ok(Some(ResolvedProp::Struct { name: prop.name.clone(), category, struct_type, default_value }))
        }
        _ => Ok(None), // ObjectProperty/ClassProperty/ArrayProperty/PointerProperty: no wire shape
    }
}

// ═══ Task 4 Step 8: TYPED_FIELDS (Location/MainScale/PostScale) shape+defaults emission ═══════════
//
// Unlike `resolve_actor_props` (Task 5), this function has no actor at all, so there is no
// stated-vs-unstated distinction to make (Step 8's own "no TYPED_FIELDS special case for
// STATEDNESS" correction) -- only "the class states a default somewhere in its Super chain" vs.
// "it doesn't, anywhere." A leaf that DOES resolve gets the exact same struct_type/category
// machinery any other `StructProperty` prop uses (`resolve_and_collect_type`, the same `types`
// closure); a leaf the class's Super chain never declares at all (no real Actor-equivalent base in
// a minimal test fixture -- real corpus always has all three) is simply absent from `props`, the
// same silent-omission behavior `TYPED_FIELD_NAMES`'s exclusion already had before this step.

/// The SEPARATE, hardcoded `TYPED_FIELDS` fallback TREE (`typed_field_fallback`'s four constants,
/// assembled into `Location`'s or `MainScale`/`PostScale`'s own real shape) -- reached only when NO
/// class in the Super chain states a default for this leaf at all. `mainscale`/`postscale` share
/// one arm: both are `Core.Scale`-shaped, and `typed_field_fallback` itself doesn't distinguish
/// between them (`transform.DEFAULT_SHEER_AXIS` etc. are the same regardless of which of the two
/// scale fields is asking).
fn typed_field_fallback_tree(name_lower: &str) -> DefaultValue {
    match name_lower {
        "location" => DefaultValue::Struct(BTreeMap::from([
            ("X".to_string(), DefaultValue::Scalar(typed_field_fallback("Location.X").to_string())),
            ("Y".to_string(), DefaultValue::Scalar(typed_field_fallback("Location.Y").to_string())),
            ("Z".to_string(), DefaultValue::Scalar(typed_field_fallback("Location.Z").to_string())),
        ])),
        "mainscale" | "postscale" => DefaultValue::Struct(BTreeMap::from([
            ("Scale".to_string(), DefaultValue::Struct(BTreeMap::from([
                ("X".to_string(), DefaultValue::Scalar(typed_field_fallback("Scale.X").to_string())),
                ("Y".to_string(), DefaultValue::Scalar(typed_field_fallback("Scale.Y").to_string())),
                ("Z".to_string(), DefaultValue::Scalar(typed_field_fallback("Scale.Z").to_string())),
            ]))),
            ("SheerRate".to_string(), DefaultValue::Scalar(typed_field_fallback("SheerRate").to_string())),
            ("SheerAxis".to_string(), DefaultValue::Scalar(typed_field_fallback("SheerAxis").to_string())),
        ])),
        other => unreachable!("typed_field_fallback_tree: not a TYPED_FIELDS name: {other}"),
    }
}

/// `MainScale`/`PostScale`'s own `SheerAxis` member, when the class states a REAL default for the
/// whole struct, decodes through the exact same generic per-kind struct-member decode every other
/// `Core.Scale`-typed property uses (`decode_one_member_value`'s `ByteProperty` arm) -- which,
/// matching CLI_STYLE (`values.py:168-171`'s `_byte_member_text`), renders a struct MEMBER byte as
/// its plain number, never an enum name. The `TYPED_FIELDS` class-schema resolver is a real,
/// deliberate EXCEPTION to that rule for exactly this one member (`gui-inspector-props-payload-
/// redesign/spec.md`'s own `Engine.Brush.MainScale` worked example: a stated `SheerAxis=0` renders
/// `"SHEER_None"`, never the plain digit `"0"`) -- an ordinary `Core.Scale`-typed property reached
/// via the GENERIC walk (e.g. `Engine.Brush.TempScale`) does NOT get this treatment and keeps the
/// plain number; this function is called ONLY from `render_typed_field`, never the generic path.
/// Finds the struct's own `SheerAxis` member (to resolve ITS enum `type_ref`) and replaces the
/// rendered ordinal text with the enum's own name at that ordinal, in place -- a no-op (leaves the
/// tree exactly as generically decoded) if the member is absent, its text isn't a bare ordinal, or
/// the ordinal is out of the enum's own range, matching every other no-fallback-invented-here
/// decode in this file.
fn canonicalize_typed_scale_sheer_axis(fqcn: &str, ctx: &ResolutionContext, prop: &DecodedProp,
    tree: DefaultValue) -> Result<DefaultValue, ResolveError> {
    let DefaultValue::Struct(mut map) = tree else { return Ok(tree) };
    let Some(DefaultValue::Scalar(text)) = map.get("SheerAxis").cloned() else {
        return Ok(DefaultValue::Struct(map));
    };
    let Ok(ordinal) = text.trim().parse::<usize>() else { return Ok(DefaultValue::Struct(map)) };
    let (owner_pkg, ti) = resolve_type_export(ctx, &prop.declaring_pkg, prop.type_ref, "Struct")?;
    let (raw, buf) = ctx.packages.get(&owner_pkg)
        .ok_or_else(|| ResolveError::MissingPackage(owner_pkg.clone()))?;
    let names: Vec<String> = raw.names.iter().map(|(n, _)| n.clone()).collect();
    let members = struct_members_with_super(fqcn, raw, buf, &names, &owner_pkg, (ti - 1) as usize)?;
    let Some(m) = members.iter().find(|m| m.name.eq_ignore_ascii_case("SheerAxis")) else {
        return Ok(DefaultValue::Struct(map));
    };
    let enum_names = resolved_enum_values(ctx, &m.declaring_pkg, m.type_ref)?;
    if let Some(name) = enum_names.get(ordinal) {
        map.insert("SheerAxis".to_string(), DefaultValue::Scalar(name.clone()));
    }
    Ok(DefaultValue::Struct(map))
}

/// One `TYPED_FIELDS` leaf (`"location"`/`"mainscale"`/`"postscale"`, case already folded by the
/// caller) -> its own `ResolvedProp::Struct`, or `None` when the class's own Super chain doesn't
/// declare a matching `StructProperty` at all. `merged` is the SAME child-first merged prop list
/// the generic walk uses (so a subclass's own override of e.g. `Location`'s category, if any, wins
/// the same way any other prop's does); `struct_type`/`types` closure collection is the exact same
/// `resolve_and_collect_type` machinery `render_prop` uses for any other `StructProperty`.
fn render_typed_field(fqcn: &str, ctx: &ResolutionContext, name_lower: &str,
    merged: &[DecodedProp], default_values: &BTreeMap<(String, i64), RenderedDefault>,
    types_out: &mut BTreeMap<String, TypeShape>, in_progress: &mut std::collections::BTreeSet<String>)
    -> Result<Option<ResolvedProp>, ResolveError> {
    let Some(prop) = merged.iter().find(|p| p.name.to_lowercase() == name_lower && p.kind == "StructProperty")
        else { return Ok(None) };
    let category = prop.category.clone().unwrap_or_else(|| "Uncategorized".to_string());
    let struct_type = resolve_and_collect_type(fqcn, ctx, prop, "Struct", types_out, in_progress)?;
    let default_value = match default_values.get(&(name_lower.to_string(), 0)) {
        Some(RenderedDefault::Tree(tree)) => {
            let tree = tree.clone();
            if name_lower == "mainscale" || name_lower == "postscale" {
                canonicalize_typed_scale_sheer_axis(fqcn, ctx, prop, tree)?
            } else {
                tree
            }
        }
        Some(RenderedDefault::Text(_)) => return Err(ResolveError::MalformedSchema {
            class: fqcn.to_string(),
            reason: format!("{}: scalar-shaped default for a TYPED_FIELDS struct", prop.name),
        }),
        None => typed_field_fallback_tree(name_lower),
    };
    Ok(Some(ResolvedProp::Struct { name: prop.name.clone(), category, struct_type, default_value }))
}

/// The real work behind `resolve_class` (below), run only on a cache miss: the Super-chain walk
/// (Steps 2-3, with the cycle guard truncating -- never erroring -- on a repeat), then the child-
/// first prop merge and the root-to-leaf defaults overlay (Steps 4-4.6).
fn resolve_class_uncached(fqcn: &str, ctx: &ResolutionContext) -> Result<ClassResolution, ResolveError> {
    struct ChainEntry {
        pkg_name: String,
        class_idx0: usize,
    }
    let mut chain: Vec<ChainEntry> = Vec::new();
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut cur: Option<String> = Some(fqcn.to_string());
    while let Some(c) = cur {
        let key = c.to_lowercase();
        if !seen.insert(key) {
            break; // Step 3's cycle guard: truncate silently, never error (matches Python exactly)
        }
        let Some((pkg_name, class_name)) = c.split_once('.') else {
            return Err(ResolveError::MalformedSchema {
                class: c.clone(), reason: "class must be fully qualified (Package.Class)".to_string(),
            });
        };
        let (raw, _buf) = ctx.packages.get(pkg_name)
            .ok_or_else(|| ResolveError::MissingPackage(pkg_name.to_string()))?;
        let names: Vec<String> = raw.names.iter().map(|(n, _)| n.clone()).collect();
        let Some(class_idx0) = find_class_export(raw, &names, class_name) else {
            return Err(ResolveError::UnresolvableClass(c.clone()));
        };
        let next = super_fqcn(raw, &names, pkg_name, class_idx0)?;
        chain.push(ChainEntry { pkg_name: pkg_name.to_string(), class_idx0 });
        cur = next;
    }

    // Props: child-first merge, case-folded collision resolved in favor of the child (Step 2/3).
    let mut merged: Vec<DecodedProp> = Vec::new();
    let mut have: std::collections::HashSet<String> = std::collections::HashSet::new();
    for entry in &chain {
        let (raw, buf) = ctx.packages.get(&entry.pkg_name).unwrap();
        let names: Vec<String> = raw.names.iter().map(|(n, _)| n.clone()).collect();
        let own = own_class_properties(fqcn, raw, buf, &names, &entry.pkg_name, entry.class_idx0)?;
        for p in own {
            if have.insert(p.name.to_lowercase()) {
                merged.push(p);
            }
        }
    }

    // Defaults: root-first overlay (leaf overrides), rendered EAGERLY per tag (Step 4) so an
    // unsupported ptype on ANY tag -- even one a later class overrides, even one whose matching
    // prop is excluded from the wire shape -- fails resolve_class, matching `resolve_class_defaults`
    // exactly (round 12/13's review).
    let mut default_values: BTreeMap<(String, i64), RenderedDefault> = BTreeMap::new();
    for entry in chain.iter().rev() {
        let (raw, buf) = ctx.packages.get(&entry.pkg_name).unwrap();
        let names: Vec<String> = raw.names.iter().map(|(n, _)| n.clone()).collect();
        let e = &raw.exports[entry.class_idx0];
        let tags = class_default_tags(buf, &names, e.soff, e.ssize)?;
        for tag in tags {
            let prop = merged.iter().find(|p| p.name.to_lowercase() == tag.name.to_lowercase());
            let rendered = render_default_tag(fqcn, ctx, &entry.pkg_name, &tag, prop)?;
            default_values.insert((tag.name.to_lowercase(), tag.array_index), rendered);
        }
    }

    let mut types: BTreeMap<String, TypeShape> = BTreeMap::new();
    // Shared across every top-level prop's own closure walk (Step 5.5's own member-cycle guard,
    // `collect_struct_type`'s doc) -- a struct fully resolved by one prop is already in `types`
    // and short-circuits before this set is even consulted, so leaving an entry in here forever
    // (never removed) is harmless; only an ACTIVELY-recursing struct is ever a false positive, and
    // that is exactly a cycle.
    let mut in_progress: std::collections::BTreeSet<String> = std::collections::BTreeSet::new();
    let mut props = Vec::new();

    // Step 8/9: TYPED_FIELDS (Location/MainScale/PostScale) FIRST, in that fixed order, ahead of
    // the generic walk below -- `render_typed_field` returns `None` (no entry, no error) for a
    // leaf this class's own Super chain never declares at all.
    for &name_lower in TYPED_FIELD_ORDER {
        match render_typed_field(fqcn, ctx, name_lower, &merged, &default_values, &mut types, &mut in_progress) {
            Ok(Some(resolved)) => props.push(resolved),
            Ok(None) => {}
            Err(ResolveError::MalformedSchema { reason, .. }) => {
                return Err(ResolveError::MalformedSchema {
                    class: fqcn.to_string(),
                    reason: format!("member {name_lower}: {reason}"),
                });
            }
            Err(other) => return Err(other),
        }
    }

    for p in &merged {
        // Step 6's name-based exclusion chain (top-level only -- see the consts' own doc above).
        let name_lower = p.name.to_lowercase();
        if HARD_REJECT.contains(&name_lower.as_str()) || TYPED_FIELD_NAMES.contains(&name_lower.as_str())
            || is_computed_key(&name_lower) {
            continue;
        }
        match render_prop(fqcn, ctx, p, &default_values, &mut types, &mut in_progress) {
            Ok(Some(resolved)) => props.push(resolved),
            Ok(None) => {}
            // Step 6.5 (owner-confirmed, not open for reinterpretation): a single unresolvable
            // struct-member/array-element LEAF fails the WHOLE resolve_class call -- never a
            // silent per-property drop or a note field. Named by the offending top-level member so
            // the message points at which property broke, not just why. MissingPackage/
            // UnresolvableClass are a DIFFERENT failure surface (the class/Super-chain itself, Step
            // 13) and propagate unchanged, never relabeled MalformedSchema.
            Err(ResolveError::MalformedSchema { reason, .. }) => {
                return Err(ResolveError::MalformedSchema {
                    class: fqcn.to_string(),
                    reason: format!("member {}: {reason}", p.name),
                });
            }
            Err(other) => return Err(other),
        }
    }

    Ok(ClassResolution { class: ResolvedClass { props }, types })
}

/// Task 4's own public entry point (spec §2's exact signature). Cache-first: a cache hit (keyed on
/// the exact `fqcn` string) returns the cached `ClassResolution` without touching
/// `resolutions_performed`; a miss increments that counter exactly once and runs the real
/// Super-chain walk (`resolve_class_uncached`) before caching and returning the result.
pub fn resolve_class(fqcn: &str, ctx: &mut ResolutionContext) -> Result<ClassResolution, ResolveError> {
    if ctx.poisoned {
        return Err(ResolveError::MalformedPackage {
            name: "<poisoned>".into(), reason: ctx.poison_reason.clone(),
        });
    }
    if let Some(cached) = ctx.class_cache.get(fqcn) {
        return Ok(cached.clone());
    }
    ctx.resolutions_performed += 1;
    let result = resolve_class_uncached(fqcn, ctx)?;
    ctx.class_cache.insert(fqcn.to_string(), result.clone());
    Ok(result)
}

// --- Task 5: resolve_actor_props ---

/// One real leaf's canonicalization need, keyed by its own dotted path (see `leaf_paths` below):
/// `None` for a plain scalar leaf (dequote only), `Some(enum_type)` for an enum-typed leaf (dequote,
/// then ordinal->name via that key's own `TypeShape::Enum` values) -- the same two real
/// canonicalizations `resolve_class` applies to defaults (spec §3's port-items list), now applied to
/// an actor's own STATED text instead.
type LeafCanon = Option<String>;

/// Every real (scalar/enum) leaf `resolve_class`'s own shape can produce, keyed by the exact dotted
/// path `_canonical_path`'s convention builds (`indexed_path`'s `"{base}.{index}"`, spec §3) --
/// struct/array CONTAINER paths are never keys here, only the leaves underneath them, matching
/// `ActorResolution.sparse`'s own leaf-only granularity. Recursion through `cr.types` is safe with no
/// cycle guard: a genuinely cyclic struct member already fails `resolve_class` itself (Step 5.5's own
/// `in_progress` guard, above) before a `ClassResolution` ever exists to walk here.
fn leaf_paths(cr: &ClassResolution) -> BTreeMap<String, LeafCanon> {
    let mut out = BTreeMap::new();
    for p in &cr.class.props {
        match p {
            ResolvedProp::Scalar { name, .. } => {
                out.insert(name.clone(), None);
            }
            ResolvedProp::Enum { name, enum_type, .. } => {
                out.insert(name.clone(), Some(enum_type.clone()));
            }
            ResolvedProp::Struct { name, struct_type, .. } => {
                collect_struct_leaf_paths(name, struct_type, &cr.types, &mut out);
            }
            ResolvedProp::Array { name, array_dim, element, .. } => {
                collect_array_leaf_paths(name, *array_dim, element, &cr.types, &mut out);
            }
        }
    }
    out
}

/// One struct-typed leaf's own members, recursively -- `prefix` is the struct's own path so far
/// (e.g. `"Data"`, or `"SurfList.2"` for one element of an array of structs). A `struct_type` not
/// present in `types` can't happen for a `ClassResolution` a successful `resolve_class` produced
/// (every struct/enum key this shape references is collected into `types` by construction, Step 5.5)
/// -- defensive, not a real path, so a miss simply contributes no leaves rather than panicking.
fn collect_struct_leaf_paths(prefix: &str, struct_type: &str, types: &BTreeMap<String, TypeShape>,
    out: &mut BTreeMap<String, LeafCanon>) {
    let Some(TypeShape::Struct { members }) = types.get(struct_type) else { return };
    for m in members {
        let path = format!("{prefix}.{}", m.name);
        match &m.kind {
            MemberKind::Scalar(_) => {
                out.insert(path, None);
            }
            MemberKind::ScalarArray { array_dim, .. } => {
                for i in 0..*array_dim {
                    out.insert(indexed_path(&path, i as i64), None);
                }
            }
            MemberKind::Struct { struct_type } => {
                collect_struct_leaf_paths(&path, struct_type, types, out);
            }
            MemberKind::Enum { enum_type } => {
                out.insert(path, Some(enum_type.clone()));
            }
            MemberKind::StructArray { array_dim, struct_type } => {
                for i in 0..*array_dim {
                    collect_struct_leaf_paths(&indexed_path(&path, i as i64), struct_type, types, out);
                }
            }
            MemberKind::EnumArray { array_dim, enum_type } => {
                for i in 0..*array_dim {
                    out.insert(indexed_path(&path, i as i64), Some(enum_type.clone()));
                }
            }
        }
    }
}

/// One top-level array leaf's own elements, `"{prefix}.{index}"` per real `array_dim` slot (never
/// run-length-collapsed, matching `resolve_class`'s own default-value convention).
fn collect_array_leaf_paths(prefix: &str, array_dim: u32, element: &ArrayElementKind,
    types: &BTreeMap<String, TypeShape>, out: &mut BTreeMap<String, LeafCanon>) {
    for i in 0..array_dim {
        let path = indexed_path(prefix, i as i64);
        match element {
            ArrayElementKind::Scalar(_) => {
                out.insert(path, None);
            }
            ArrayElementKind::Enum(key) => {
                out.insert(path, Some(key.clone()));
            }
            ArrayElementKind::Struct(key) => {
                collect_struct_leaf_paths(&path, key, types, out);
            }
        }
    }
}

/// `propedit/base.py:50-58`'s `_dequote`: strip ONE genuine wrapping quote pair (a leading+trailing
/// `"` strips only when the interior holds no further `"`) -- otherwise just the surrounding
/// whitespace. An actor's own stated text is real T3D quoting syntax to strip; a class DEFAULT
/// (`resolve_class`'s own job) never sees this at all (see `resolve_class_str_default_is_never_
/// dequoted` above) -- the two functions deliberately disagree here.
fn dequote(s: &str) -> String {
    let t = s.trim();
    if t.len() >= 2 && t.starts_with('"') && t.ends_with('"') && !t[1..t.len() - 1].contains('"') {
        t[1..t.len() - 1].to_string()
    } else {
        t.to_string()
    }
}

/// `propedit/edit.py:50-58`'s `_canonicalize_enum`: an already-dequoted stored ordinal -> its NAME;
/// anything else (already a name, out of range, or not digit text at all) passes through unchanged.
/// Matches `_canonicalize_enum`'s own `isdigit()` check with ASCII digits only, not Python's wider
/// unicode-digit `isdigit()` -- Step 3.5's own noted, vanishingly-remote real divergence (real T3D
/// text is always decimal ASCII), not worth a defensive path here.
fn canonicalize_stated_enum(dequoted: &str, enum_type: &str, types: &BTreeMap<String, TypeShape>) -> String {
    let Some(TypeShape::Enum { values }) = types.get(enum_type) else { return dequoted.to_string() };
    if !dequoted.is_empty() && dequoted.bytes().all(|b| b.is_ascii_digit()) {
        if let Ok(i) = dequoted.parse::<usize>() {
            if let Some(name) = values.get(i) {
                return name.clone();
            }
        }
    }
    dequoted.to_string()
}

/// Spec §2's exact signature -- never returns `Err`. Resolves `actor_cls`'s own shape (via
/// `resolve_class`, cached in `ctx` the same as any other caller), then does its own cheap per-actor
/// work: keep only `actor_props` entries whose path exists in that shape (an orphan path is a silent
/// skip, spec §2/§3), canonicalizing each kept value the same way `resolve_class` canonicalizes
/// defaults (enum ordinal->name, `_dequote`).
///
/// A whole-class resolve failure (missing package, unresolvable class, malformed schema) degrades to
/// `ActorResolution { sparse: {}, note: Some(msg) }` instead of propagating -- `effective_props.py:
/// 208-224`'s own contract, so one broken actor never fails a whole `/scene` request. `msg`'s exact
/// text is pinned byte-for-byte against the real Python `f"actor {actor.name!r}: schema unavailable
/// ({actor.cls}) — cannot resolve effective props ({e})"` (`effective_props.py:222-224`) -- LITERAL
/// single quotes around `actor_name` (Python's `!r`), never Rust's `{:?}` debug format (which would
/// emit double quotes instead and silently break every degraded-actor golden comparison, Tasks 6/7).
///
/// Precondition: paths in `actor_props` must already match the resolved schema's own exact spelling
/// (case-sensitive); the caller is responsible for any normalization before calling this function --
/// an unmatched path is silently treated as an orphan and dropped, not an error.
pub fn resolve_actor_props(actor_name: &str, actor_cls: &str, actor_props: &[(String, String)],
    ctx: &mut ResolutionContext) -> ActorResolution {
    let class_resolution = match resolve_class(actor_cls, ctx) {
        Ok(cr) => cr,
        Err(e) => {
            let reason = e.to_string();
            return ActorResolution {
                sparse: BTreeMap::new(),
                note: Some(format!(
                    "actor '{actor_name}': schema unavailable ({actor_cls}) — cannot resolve effective props ({reason})"
                )),
            };
        }
    };
    let leaves = leaf_paths(&class_resolution);
    let mut sparse = BTreeMap::new();
    for (path, raw_value) in actor_props {
        let Some(canon) = leaves.get(path) else { continue }; // orphan path: silently skip
        let dequoted = dequote(raw_value);
        let value = match canon {
            Some(enum_type) => canonicalize_stated_enum(&dequoted, enum_type, &class_resolution.types),
            None => dequoted,
        };
        sparse.insert(path.clone(), value);
    }
    ActorResolution { sparse, note: None }
}

#[cfg(test)]
pub(super) mod context_fixture {
    const MAGIC: u32 = 0x9E2A83C1;   // duplicated from package_read.rs -- see Task 4 Step 0's
    const HEADER_FIXED: usize = 36;  // identical module doc for why this is deliberate.

    fn encode_compact_index(v: i64) -> Vec<u8> {   // identical to Task 4 Step 0's -- if Task 4
        let neg = v < 0;                            // lands first, import it instead of
        let mut mag = v.unsigned_abs();              // re-defining; whichever task lands SECOND
        let mut first = (mag & 0x3F) as u8;           // reuses the other's, no duplicate logic
        mag >>= 6;                                    // ships in the final crate either way.
        if neg { first |= 0x80; }
        if mag != 0 { first |= 0x40; }
        let mut out = vec![first];
        while mag != 0 {
            let mut b = (mag & 0x7F) as u8;
            mag >>= 7;
            if mag != 0 { b |= 0x80; }
            out.push(b);
        }
        out
    }

    /// A package with a name table (starting "None" at index 0) and an import table built from
    /// `imports`: each `(class_name, package_name)` becomes one import entry whose ClassName is
    /// `class_name` and whose PackageIndex chain resolves to `package_name` (a second, synthetic
    /// "owning package" import entry per distinct `package_name`, PackageIndex=0 on that owner
    /// entry, and the real entry's PackageIndex pointing at it) -- exercises package_imports's
    /// real outer-chain walk, not a shortcut.
    pub(super) fn synthetic_package_with_imports(imports: &[(&str, &str)]) -> Vec<u8> {
        let mut names = vec!["None".to_string()];
        let mut owner_index_of: std::collections::BTreeMap<&str, i32> = std::collections::BTreeMap::new();
        let mut import_entries: Vec<(i64, i64, i32, i64)> = Vec::new(); // (class_pkg, class_name, pkg_idx, obj_name)
        for &(_, pkg) in imports {                    // destructure THROUGH the reference so
            owner_index_of.entry(pkg).or_insert_with(|| {   // `pkg`/`cls` bind as `&str`, not
                names.push(pkg.to_string());                 // `&&str` -- `.entry()` needs an
                let obj_name_idx = (names.len() - 1) as i64; // exact `&str` key.
                import_entries.push((0, 0, 0, obj_name_idx)); // this import IS the package (PackageIndex=0)
                import_entries.len() as i32 // 1-based import index for the negative-ref convention
            });
        }
        for &(cls, pkg) in imports {
            names.push(cls.to_string());
            let class_name_idx = (names.len() - 1) as i64;
            let owner_import_1based = owner_index_of[pkg];
            import_entries.push((0, class_name_idx, -owner_import_1based, class_name_idx));
        }

        let mut names_blob = Vec::new();
        for n in &names {
            names_blob.extend_from_slice(&encode_compact_index(n.len() as i64));
            names_blob.extend_from_slice(n.as_bytes());
            names_blob.extend_from_slice(&0u32.to_le_bytes());
        }
        let mut imports_blob = Vec::new();
        for (cp, cn, pi, on) in &import_entries {
            imports_blob.extend_from_slice(&encode_compact_index(*cp));
            imports_blob.extend_from_slice(&encode_compact_index(*cn));
            imports_blob.extend_from_slice(&pi.to_le_bytes());
            imports_blob.extend_from_slice(&encode_compact_index(*on));
        }

        let name_offset = HEADER_FIXED + 16;
        let import_offset = name_offset + names_blob.len();
        let mut buf = vec![0u8; name_offset];
        buf[0..4].copy_from_slice(&MAGIC.to_le_bytes());
        buf[4..8].copy_from_slice(&69u32.to_le_bytes());
        buf[8..12].copy_from_slice(&0u32.to_le_bytes());
        buf[12..16].copy_from_slice(&(names.len() as u32).to_le_bytes());
        buf[16..20].copy_from_slice(&(name_offset as u32).to_le_bytes());
        buf[20..24].copy_from_slice(&0u32.to_le_bytes()); // expcnt=0
        buf[24..28].copy_from_slice(&(import_offset as u32).to_le_bytes()); // expoff (unused)
        buf[28..32].copy_from_slice(&(import_entries.len() as u32).to_le_bytes());
        buf[32..36].copy_from_slice(&(import_offset as u32).to_le_bytes());
        buf.extend_from_slice(&names_blob);
        buf.extend_from_slice(&imports_blob);
        buf
    }
}

#[cfg(test)]
pub(super) mod fixture {
    const MAGIC: u32 = 0x9E2A83C1;          // duplicated from package_read.rs -- see module doc above
    const HEADER_FIXED: usize = 36;

    /// Real FCompactIndex encoder, the exact inverse of `package_read::read_compact_index`
    /// (`package_read.rs:16-39`): byte 0 = sign(bit7) | continuation(bit6) | low 6 bits;
    /// each following byte = continuation(bit7) | next 7 bits. Handles any magnitude the DECODER
    /// itself round-trips (up to 2^34, per `read_compact_index`'s own `shift >= 27` cutoff at
    /// `package_read.rs:32` -- five 7-bit continuation groups after the 6-bit first byte) -- this
    /// fixture builder never assumes single-byte encoding, and no fixture built here comes close
    /// to that bound regardless.
    pub(super) fn encode_compact_index(v: i64) -> Vec<u8> {
        let neg = v < 0;
        let mut mag = v.unsigned_abs();
        let mut first = (mag & 0x3F) as u8;
        mag >>= 6;
        if neg { first |= 0x80; }
        if mag != 0 { first |= 0x40; }
        let mut out = vec![first];
        while mag != 0 {
            let mut b = (mag & 0x7F) as u8;
            mag >>= 7;
            if mag != 0 { b |= 0x80; }
            out.push(b);
        }
        out
    }

    /// One `Dependencies` TArray entry (`uclass.py:309-312`):
    /// `(ClassRef:compact, Deep:u32, ScriptTextCRC:u32)`.
    pub(super) struct DependencyEntry { pub class_ref: i64, pub deep: u32, pub crc: u32 }

    /// The UClass body HEADER that precedes any class's own default-tag block (per
    /// `uclass.py:298-322`'s exact field order) — **NOT a fixed 63 bytes** (an earlier draft's
    /// `CLASS_BODY_HEADER_LEN = 63` assumed `Dependencies`/`PackageImports` are always empty;
    /// round 10's review measured the real corpus and found EVERY class has both non-empty --
    /// `Engine.u` 88/88, `DeusEx.u` 1166/1166, `core.u` 7/7 — so this header's real length varies
    /// per class and must be computed from THIS call's own `deps`/`pkg_imports`/`script_bin`
    /// lengths, never assumed): 5 null compact refs (SuperField/Next/ScriptText/Children/
    /// FriendlyName, 1 byte each) + `Line:u32` + `TextPos:u32` + `ScriptSize:u32` + `script_bin`
    /// itself + UState's 22 zero bytes + `ClassFlags`+`ClassGuid`'s 20 zero bytes + `Dependencies`
    /// TArray (compact count + count × `{ClassRef:compact, Deep:u32, CRC:u32}`) + `PackageImports`
    /// TArray (compact count + count × `name:compact`) + `ClassWithin:compact` +
    /// `ClassConfigName:compact`. **`script_mem_size` is a SEPARATE parameter from
    /// `script_bin.len()`** (round 11's review, C2) — `ScriptSize` is the bytecode's IN-MEMORY
    /// size, `script_bin` is its ON-DISK bytes, and these genuinely differ for any real script
    /// containing a compact-encoded ref (a variable-width disk form, fixed 4 bytes in memory) --
    /// measured: 16/16 real `Engine.u` classes with a non-empty script diverge (`Engine.Actor`:
    /// 767 mem / 624 disk bytes). Passing `script_mem_size = script_bin.len() as u32` reproduces
    /// only the (unrepresentative) no-divergence case; a test that needs to prove the walker
    /// actually handles the divergence (Step 0.5's own Test 3, and at least one Step 0.6 test)
    /// must pass a REAL divergent pair — build `script_bin` by hand from real opcodes (Step 0.5's
    /// own `ObjectConst`/`0x20` example: 2 disk bytes, 5 memory bytes) and pass the CORRECT
    /// in-memory total as `script_mem_size` separately, not derived from `script_bin.len()`.
    /// Returns ONLY the header bytes (not the trailing tag block) — callers use `.len()` on the
    /// result to find where the tag block starts, computed fresh per call, never a shared constant.
    /// `class_within`/`class_config_name` are name-table indices for `ClassWithin`/
    /// `ClassConfigName` (Step 0.6 Test 5 — real classes never have either at 0; pass 0 for a
    /// test that doesn't care about either value).
    pub(super) fn class_body_header(script_bin: &[u8], script_mem_size: u32,
                                      deps: &[DependencyEntry], pkg_imports: &[i64],
                                      class_within: i64, class_config_name: i64) -> Vec<u8> {
        let mut b = vec![0u8; 5]; // SuperField/Next/ScriptText/Children/FriendlyName -- all "None"
        b.extend_from_slice(&0u32.to_le_bytes());                        // Line
        b.extend_from_slice(&0u32.to_le_bytes());                        // TextPos
        b.extend_from_slice(&script_mem_size.to_le_bytes());              // ScriptSize -- IN-MEMORY,
                                                                            // NOT script_bin.len()
        b.extend_from_slice(script_bin);
        b.extend_from_slice(&[0u8; 22]); // UState: ProbeMask+IgnoreMask+LabelTableOffset+StateFlags
        b.extend_from_slice(&[0u8; 20]); // ClassFlags + ClassGuid
        b.extend_from_slice(&encode_compact_index(deps.len() as i64));
        for d in deps {
            b.extend_from_slice(&encode_compact_index(d.class_ref));
            b.extend_from_slice(&d.deep.to_le_bytes());
            b.extend_from_slice(&d.crc.to_le_bytes());
        }
        b.extend_from_slice(&encode_compact_index(pkg_imports.len() as i64));
        for &n in pkg_imports { b.extend_from_slice(&encode_compact_index(n)); }
        b.extend_from_slice(&encode_compact_index(class_within));
        b.extend_from_slice(&encode_compact_index(class_config_name));
        b
    }

    /// One property export's body per `_decode_property` (`ufield.py:14-58`): a tagged-prop
    /// HEADER (usually just a bare "None" terminator, but NOT always — see below), SuperField/Next
    /// (0), ArrayDim, PropertyFlags=0, Category, and `type_ref` (only when `Some`). `header` is
    /// ALREADY-ENCODED bytes (typically `&none_terminator(0)` for the common case), NOT just a
    /// name index — `ufield.py:32-35` documents a REAL corpus exception: `Engine.Actor.Touching`
    /// carries a real `IntProperty` tag named `"0"` BEFORE its own "None" terminator ("reading one
    /// compact as the terminator desyncs every later field" — a live finding, not a hypothetical).
    /// A production `_decode_property` port must read this header via `read_property_tags` over
    /// `[soff, soff+ssize)` (the SAME function used everywhere else in this plan for a tagged-prop
    /// list), NOT a single `read_compact_index` call assuming it's always bare — this fixture
    /// builder's own `header: &[u8]` parameter exists specifically so a test CAN build the
    /// Touching-shaped case (pass `encode_fixed_tag(...) + none_terminator(0)` instead of just
    /// `&none_terminator(0)`) and catch a production decoder that assumes bare-only. `category_idx`
    /// is a name-table index.
    pub(super) fn property_body(header: &[u8], array_dim: u32, property_flags: u32,
                                  category_idx: i64, rep_offset: u16, type_ref: Option<i64>) -> Vec<u8> {
        let mut b = header.to_vec();                           // tagged-prop header -- see doc above
        b.extend_from_slice(&encode_compact_index(0));         // SuperField
        b.extend_from_slice(&encode_compact_index(0));         // Next
        b.extend_from_slice(&array_dim.to_le_bytes());
        b.extend_from_slice(&property_flags.to_le_bytes());
        b.extend_from_slice(&encode_compact_index(category_idx));
        const CPF_NET: u32 = 0x20; // uprops/base.py:26 -- PropertyFlags bit: a 2-byte RepOffset
        // `rep_offset` is a REAL parameter (round 12's review, I2: a hardcoded 0u16 here made
        // Step 6.6(b)'s own test vacuous -- with RepOffset bytes `00 00`, a decoder that WRONGLY
        // skips no bytes reads `type_ref` starting at `00 00 <type_ref bytes>`, and since
        // `_last_compact` reads to BODY END regardless of where it starts, a leading `0x00` byte
        // is itself a valid (if wasteful) zero-continuation compact-index prefix that still
        // decodes to the SAME final value -- the bug is invisible with an all-zero RepOffset. A
        // value whose bytes genuinely corrupt the read (e.g. `0x8040`: low byte `0x40` sets the
        // compact-index CONTINUATION bit, chaining into what should have been `type_ref`'s own
        // first byte) is what actually distinguishes "skipped correctly" from "not skipped".
        if property_flags & CPF_NET != 0 { b.extend_from_slice(&rep_offset.to_le_bytes()); }
        if let Some(tr) = type_ref { b.extend_from_slice(&encode_compact_index(tr)); }
        b
    }

    /// Like `property_body` but with an explicit `next_ref` (the `UField.Next` compact ref) --
    /// needed to chain sibling members in a Struct's `Children` linked list (`ufield.py:263-271`'s
    /// `_field_next`: `[tagged-prop header][SuperField][Next]…`, so `Next` is the SECOND field
    /// after the header, same position `property_body` already writes `SuperField` at; `_field_next`
    /// ALSO reads its header via `read_property_tags`, same real-corpus exception as `property_body`
    /// above — a production port must not special-case this function to assume bare-only either).
    /// `PropertyFlags` is always 0 here (no `CPF_NET` parameter, unlike `property_body`) --
    /// struct MEMBERS aren't independently net-replicated the way a top-level class property can
    /// be, and no test in this plan needs a struct member with a `RepOffset`; add the parameter
    /// the same way `property_body` has it if a future step genuinely needs one.
    pub(super) fn property_body_chained(header: &[u8], next_ref: i64, array_dim: u32,
                                          category_idx: i64, type_ref: Option<i64>) -> Vec<u8> {
        let mut b = header.to_vec();                           // tagged-prop header -- see doc above
        b.extend_from_slice(&encode_compact_index(0));          // SuperField
        b.extend_from_slice(&encode_compact_index(next_ref));   // Next -- chains to the following
        b.extend_from_slice(&array_dim.to_le_bytes());            // sibling member's export index
        b.extend_from_slice(&0u32.to_le_bytes());                  // PropertyFlags = 0, see doc above
        b.extend_from_slice(&encode_compact_index(category_idx));
        if let Some(tr) = type_ref { b.extend_from_slice(&encode_compact_index(tr)); }
        b
    }

    /// Accumulates a package's name/import/export tables and assembles real bytes in one pass.
    /// Every offset is computed from ACTUAL encoded lengths, never assumed.
    #[derive(Default)]
    pub(super) struct FixtureBuilder {
        names: Vec<String>,                                  // index 0 reserved for "None" (see new())
        imports: Vec<(i64, i64, i32, i64)>,                   // (class_pkg, class_name, pkg_idx, obj_name)
        exports: Vec<(i64, i64, i32, i64, u32, Vec<u8>)>,     // (cls, sup, outer, nm, flags, body)
        pkg_owner_imports: std::collections::BTreeMap<String, i32>, // pkg_name -> its 1-based
                                                                        // "owning" import index,
                                                                        // used by import_type_in_package
                                                                        // to reuse one owner entry
                                                                        // per distinct package.
    }

    impl FixtureBuilder {
        pub(super) fn new() -> Self { Self { names: vec!["None".to_string()], ..Default::default() } }

        /// Interns `s`, returning its name-table index (reuses an existing entry if present).
        pub(super) fn name(&mut self, s: &str) -> i64 {
            if let Some(i) = self.names.iter().position(|n| n == s) { return i as i64; }
            self.names.push(s.to_string());
            (self.names.len() - 1) as i64
        }

        /// Pushes `s` into the name table WITHOUT deduping against an existing entry -- unlike
        /// `name()`, which always reuses an existing index. Needed for Step 10's real corpus
        /// inverse case: TWO DIFFERENT name-table slots that both spell the same text (e.g. a
        /// second, genuinely distinct "None" entry, unrelated to index 0's own special meaning) --
        /// `name()`'s own dedup can never produce that shape (a second `name("None")` call just
        /// reuses index 0).
        pub(super) fn push_name_allow_duplicate(&mut self, s: &str) -> i64 {
            self.names.push(s.to_string());
            (self.names.len() - 1) as i64
        }

        /// Adds an import for a `*Property`/`Class`/`Struct`/`Enum`-typed reference, e.g.
        /// `import_type("IntProperty")`. Returns the NEGATIVE-ONE-BASED `cls`/outer-style ref
        /// (`-(1-based import index)`) this import's own name-table entry can be addressed by --
        /// package_read.rs's own convention for a compact object reference (0=None, >0=export
        /// index+1, <0=`-(import index+1)`), matching `read_compact_index`'s decode and
        /// `upackage.py:110-123`'s `name_of_ref` on the Python side.
        pub(super) fn import_type(&mut self, type_name: &str) -> i64 {
            let obj_name = self.name(type_name);
            // class_pkg/class_name (0/0) are left as "None" -- Task 3 Step 6's own package_imports
            // filter DOES read this entry's class_name field (to decide Class/Struct/Enum/
            // *Property-ness), so an import built here would be filtered OUT of that function's
            // own results; that's fine, `import_type` exists for resolve_class's OWN internal
            // type-ref resolution, not for exercising package_imports (Task 3's own fixtures do
            // that, with real class_name values). PackageIndex=0 means this import's OWN name IS
            // its "package" -- correct only for a same-package reference; use
            // `import_type_in_package` for a cross-package one.
            self.imports.push((0, 0, 0, obj_name));
            -(self.imports.len() as i64)
        }

        /// Adds a Class export with EMPTY `script_bin`/`deps`/`pkg_imports` (structurally valid —
        /// `class_default_tags` doesn't care whether these are empty — but NOT representative of
        /// any real class; use `add_class_ex` directly for a test that needs real non-zero ones,
        /// e.g. Step 0.6's own dedicated test). Thin wrapper kept because most of this plan's
        /// steps only need the SHAPE (Super chain, identity, exclusion) right, not full
        /// defaults-decode realism. `sup` is a signed object ref (0 = no Super, or another
        /// `add_class`/`add_class_ex` call's returned index for a Super chain). `extra_tag_bytes`
        /// may be `&[]` for a class with no stated defaults — `class_default_tags`
        /// (`uclass.py:294-322`) only short-circuits on `ssize <= 0` (never true here, the header
        /// alone is always well over 0 bytes), so it always tries to decode a tagged-property
        /// list at the body's tail; `add_class_ex` appends the `[0x00]` "None" terminator itself
        /// when `extra_tag_bytes` is EMPTY. Returns the 1-based export index.
        pub(super) fn add_class(&mut self, class_name: &str, sup: i64, extra_tag_bytes: &[u8]) -> i64 {
            self.add_class_ex(class_name, sup, &[], 0, &[], &[], 0, 0, extra_tag_bytes)
        }

        /// The full-featured Class export builder — `script_bin` (Step 0.5's walked bytecode
        /// blob, `&[]` for a script-free class) and `script_mem_size` (its SEPARATE in-memory
        /// size, per `class_body_header`'s own doc — do not pass `script_bin.len() as u32` for a
        /// test that needs to prove real disk/memory divergence is handled), `deps`/`pkg_imports`
        /// (Step 0.6's `Dependencies`/`PackageImports` TArray content, `&[]` structurally valid
        /// but not representative of any real class — see `class_body_header`'s own doc for the
        /// measured 100% figure), `class_within`/`class_config_name` (name-table indices, 0 if a
        /// test doesn't care about either — see `class_body_header`'s own doc, Step 0.6 Test 5),
        /// `extra_tag_bytes` (the class's own default-tag block, same convention as `add_class`).
        pub(super) fn add_class_ex(&mut self, class_name: &str, sup: i64, script_bin: &[u8],
                                     script_mem_size: u32, deps: &[DependencyEntry],
                                     pkg_imports: &[i64], class_within: i64, class_config_name: i64,
                                     extra_tag_bytes: &[u8]) -> i64 {
            let nm = self.name(class_name);
            let mut body = class_body_header(script_bin, script_mem_size, deps, pkg_imports,
                class_within, class_config_name);
            body.extend_from_slice(extra_tag_bytes);
            if extra_tag_bytes.is_empty() { body.push(0x00); } // bare "None" terminator: index 0
            self.exports.push((0, sup, 0, nm, 0, body));   // cls=0 ("this IS a class"), outer=0
            self.exports.len() as i64
        }

        /// Adds a `*Property` export (e.g. `add_property("iLeaf", "IntProperty", class_idx, 1,
        /// "Uncategorized", None)`). `outer_class_idx` is a PREVIOUS `add_class` call's returned
        /// index. `type_ref` is `Some(signed ref)` for struct/object/class/array kinds AND for a
        /// `ByteProperty` that carries an ENUM (`type_name: "ByteProperty"`, `type_ref:
        /// Some(enum_export_idx)`) -- `None` for a PLAIN byte (no enum) and for
        /// int/float/name/string. See Step 0's own header comment for the real citation
        /// (`_KINDS_WITH_TYPE_REF`, `uprops/base.py:21-23`).
        pub(super) fn add_property(&mut self, prop_name: &str, type_name: &str, outer_class_idx: i64,
                                     array_dim: u32, category: &str, type_ref: Option<i64>) -> i64 {
            self.add_property_ex(prop_name, type_name, outer_class_idx, &none_terminator(0),
                array_dim, 0, category, 0, type_ref)
        }

        /// Full-featured variant exposing `header` (a REAL leading tag before the terminator, for
        /// Step 6.6's `Engine.Actor.Touching`-shaped test — `add_property`'s own thin wrapper
        /// always passes a bare `none_terminator(0)`), `property_flags` (for Step 6.6's own
        /// `CPF_NET` test: `property_flags: 0x20` triggers the 2-byte `RepOffset` skip
        /// `property_body` already implements), AND `rep_offset` (see `property_body`'s own doc
        /// for why an all-zero `RepOffset` makes the `CPF_NET` test vacuous — pass a REAL breaking
        /// value like `0x8040` when this test's whole point is to prove the skip happened). This
        /// is the entry point Step 6.6 needs — `FixtureBuilder::exports` is private, so a test
        /// can't push a pre-built body directly; this method is the sanctioned way to reach
        /// `property_body`'s full parameter set.
        pub(super) fn add_property_ex(&mut self, prop_name: &str, type_name: &str,
            outer_class_idx: i64, header: &[u8], array_dim: u32, property_flags: u32,
            category: &str, rep_offset: u16, type_ref: Option<i64>) -> i64 {
            let nm = self.name(prop_name);
            let cat_idx = self.name(category);
            let cls = self.import_type(type_name);
            let body = property_body(header, array_dim, property_flags, cat_idx, rep_offset, type_ref);
            self.exports.push((cls, 0, outer_class_idx as i32, nm, 0, body));
            self.exports.len() as i64
        }

        /// Like `add_property_ex` but takes an EXPLICIT category name-table index instead of
        /// interning a category string -- needed for Step 10's real corpus inverse case: a
        /// category whose name-table index is NON-ZERO but whose TEXT also happens to spell
        /// "None" (a genuine duplicate entry, built via `push_name_allow_duplicate`, distinct from
        /// index 0's own special "None" slot). `add_property_ex`'s own `category: &str` always
        /// interns via the deduping `name()`, which can never address a SPECIFIC duplicate slot --
        /// this is the sanctioned lower-level path for a test that needs to.
        pub(super) fn add_property_with_category_idx(&mut self, prop_name: &str, type_name: &str,
            outer_class_idx: i64, array_dim: u32, category_idx: i64, type_ref: Option<i64>) -> i64 {
            let nm = self.name(prop_name);
            let cls = self.import_type(type_name);
            let body = property_body(&none_terminator(0), array_dim, 0, category_idx, 0, type_ref);
            self.exports.push((cls, 0, outer_class_idx as i32, nm, 0, body));
            self.exports.len() as i64
        }

        /// The 1-based export index the NEXT `add_class`/`add_property`/`add_enum` call will
        /// return, WITHOUT adding anything yet. **Does NOT predict `add_struct_with_members`'s
        /// own return** -- that call pushes `members.len()` member exports BEFORE the struct
        /// export itself, so its actual return is `next_export_index() + members.len()`, not
        /// `next_export_index()` (an earlier draft of this method's own doc got this wrong,
        /// causing every downstream prediction built on it to be off by `members.len()`). Exists
        /// to break a genuine mutual reference this builder otherwise cannot express (e.g. Step
        /// 8's `Scale`/`ESheerAxis`: the enum's own `outer` must be the struct's index, but a
        /// member INSIDE that struct needs the enum's index as its `type_ref` -- each side needs
        /// the other's index before it exists). Compute the target's future index with this
        /// method (adjusted by `+ members.len()` if the target is itself an
        /// `add_struct_with_members` call) FIRST, use it as a forward reference in whichever side
        /// is built first, then build the other side for real and `assert_eq!` the prediction
        /// against its REAL returned index before trusting it further -- a compact-index
        /// reference is just a number, it doesn't care whether the export it points at has been
        /// written yet, but a wrong prediction silently references the wrong export with no
        /// compile-time or parse-time signal.
        pub(super) fn next_export_index(&self) -> i64 { self.exports.len() as i64 + 1 }

        /// Adds an import for a `*Property`/`Class`/`Struct`/`Enum` reference belonging to
        /// ANOTHER package (unlike `import_type`, which is only correct for a same-package
        /// reference — `import_type`'s hardcoded `PackageIndex=0` makes `import_package_of` return
        /// the object's own name as its "package", so it can never express a cross-package Super
        /// or type ref). Builds the SAME two-entry owner chain `context_fixture::
        /// synthetic_package_with_imports` (Task 3 Step 0) already establishes: a synthetic
        /// "owning package" import (reused across calls with the same `pkg_name`, `PackageIndex=0`
        /// on THAT entry) plus the real type import whose `PackageIndex` points at it.
        pub(super) fn import_type_in_package(&mut self, type_name: &str, pkg_name: &str) -> i64 {
            let pkg_import_1based = if let Some(i) = self.pkg_owner_imports.get(pkg_name) {
                *i
            } else {
                let obj_name = self.name(pkg_name);
                self.imports.push((0, 0, 0, obj_name));
                let idx = self.imports.len() as i32;
                self.pkg_owner_imports.insert(pkg_name.to_string(), idx);
                idx
            };
            let obj_name = self.name(type_name);
            self.imports.push((0, 0, -pkg_import_1based, obj_name));
            -(self.imports.len() as i64)
        }

        /// Adds a Struct export with real members, linked via the Children/Next chain
        /// `struct_members` (`ufield.py:300-330`) actually walks — NOT via `outer`-scan the way
        /// top-level class properties are found (`own_class_properties` never looks at Children).
        /// `outer` is the struct's own outer ref (0 for a top-level struct in this package, or
        /// another `import_type_in_package`/`add_class` result for a nested/imported context —
        /// spec §1's identity rule reads THIS field). `sup` is a LOCAL super-struct's own export
        /// index (0 = no super; a POSITIVE ref, matching `struct_members`' own `sup_ref > 0`
        /// branch, `ufield.py:316-317` — `sup_ref < 0`, an IMPORTED super-struct, raises
        /// `SchemaError` in the real Python and is correctly out of scope for this port too, per
        /// that same function's own `"imported super-struct not supported"` line). `members` is
        /// `(name, type_name, array_dim, category, type_ref)` tuples, declaration order — THIS
        /// struct's OWN members only, NOT including whatever `sup` itself declares (the
        /// production `struct_members` port prepends the super's members recursively; build the
        /// super struct SEPARATELY via its own `add_struct_with_members` call and pass its
        /// returned index as `sup` here — see Step 5.6 for why this recursion is a REAL,
        /// separately-ported mechanism, not just a fixture nicety: `Core.Plane extends Core.Vector`
        /// is the real corpus shape, on 100% of the golden subset's classes via `Engine.Actor
        /// .SimAnim`). Returns the struct's own export index (use as a property's `type_ref` via a
        /// positive local ref, or via `import_type_in_package` from another package).
        pub(super) fn add_struct_with_members(&mut self, struct_name: &str, outer: i32, sup: i64,
            members: &[(&str, &str, u32, &str, Option<i64>)]) -> i64 {
            self.add_struct_with_members_ex(struct_name, outer, sup, members, None)
        }

        /// Full-featured `add_struct_with_members` -- `leading_sibling`, when `Some`, is an
        /// ALREADY-BUILT non-property export (e.g. from `add_enum_ex`) to splice at the HEAD of
        /// this struct's own `Children` chain, ahead of every real member -- a real corpus shape
        /// (round 15's review: `Core.Scale`'s own chain is `ESheerAxis (Enum) -> Scale ->
        /// SheerRate -> SheerAxis`, the enum sitting FIRST). The sibling's OWN `Next` field must
        /// already have been built pointing at what will become this call's first member's index
        /// (predict it via `next_export_index()` the same way Step 8's mutual Scale/ESheerAxis
        /// reference already does) -- this function does not patch it, since the sibling's body
        /// is already-serialized bytes by the time this runs. `None` reproduces plain
        /// `add_struct_with_members`'s behavior exactly (`Children` = the first real member).
        pub(super) fn add_struct_with_members_ex(&mut self, struct_name: &str, outer: i32,
            sup: i64, members: &[(&str, &str, u32, &str, Option<i64>)],
            leading_sibling: Option<i64>) -> i64 {
            // Build members LAST-TO-FIRST so each one's `next_ref` is the ALREADY-KNOWN export
            // index of the member declared right after it (0 for the last member -- chain
            // terminator, per `_field_next`'s own `nxt == 0` stop condition).
            let mut next_ref = 0i64;
            let mut first_member_idx = 0i64;
            for &(prop_name, type_name, array_dim, category, type_ref) in members.iter().rev() {
                let nm = self.name(prop_name);
                let cat_idx = self.name(category);
                let cls = self.import_type(type_name);
                let body = property_body_chained(&none_terminator(0), next_ref, array_dim, cat_idx, type_ref);
                self.exports.push((cls, 0, 0, nm, 0, body)); // outer patched below, once the
                first_member_idx = self.exports.len() as i64; // struct's own index is known
                next_ref = first_member_idx;
            }
            let struct_nm = self.name(struct_name);
            // Struct body per `struct_children_ref` (`ufield.py:274-285`):
            // [None][SuperField][Next][ScriptText][Children].
            let mut body = encode_compact_index(0);              // None
            body.extend_from_slice(&encode_compact_index(sup)); // SuperField -- 0 = no super,
                                                                   // positive = a LOCAL super
                                                                   // struct's own export index.
            body.extend_from_slice(&encode_compact_index(0)); // Next
            body.extend_from_slice(&encode_compact_index(0)); // ScriptText
            // Children: the leading sibling if one was given, else the first real member --
            // matches struct_members' own walk, which starts here and skips non-property exports
            // (Step 5.65's own new "skip but follow Next" requirement).
            body.extend_from_slice(&encode_compact_index(leading_sibling.unwrap_or(first_member_idx)));
            // cls MUST resolve (via name_of_ref) to the literal string "Struct" --
            // find_struct_export (ufield.py:288-296) checks this exactly; cls=0/None does NOT
            // satisfy it (unlike a Class export, where cls=0 IS the "this is a class" marker).
            let struct_cls = self.import_type("Struct");
            self.exports.push((struct_cls, sup, outer, struct_nm, 0, body)); // `sup` in the EXPORT
                                                                                 // TABLE tuple, not
                                                                                 // just the body's own
                                                                                 // SuperField -- see below.
            let struct_idx = self.exports.len() as i64;
            // Now patch every member's `outer` to this struct's own index (own_class_properties'
            // sibling concept for structs -- members' outer must point at their OWN struct, per
            // the same export-table convention, even though struct_members reads them via
            // Children/Next, not outer-scan; leaving outer=0 would misrepresent a real package).
            // `struct_idx = base + N + 1` where `base` is the members' own starting 0-based index
            // and N = members.len(), so the first member's 0-based index is `struct_idx - 1 - N`.
            let first = struct_idx as usize - 1 - members.len();
            for i in first..(struct_idx as usize - 1) {
                self.exports[i].2 = struct_idx as i32;
            }
            struct_idx
        }

        /// Adds an Enum export with `values` (ordered), `outer` its OWN export-record outer ref
        /// (0 for a top-level enum, or a class/struct's own export index -- REQUIRED, not
        /// optional: spec §1's identity rule keys an enum's canonical name on this field exactly
        /// the same way it keys a struct's, e.g. `Core.Scale.ESheerAxis`'s `Scale` component
        /// comes from `ESheerAxis`'s own `outer` pointing at the `Scale` struct, not from any
        /// import; round 5's version hardcoded `outer=0`, which can only ever produce
        /// `Core.ESheerAxis` and would make Step 8's own required test pass vacuously against the
        /// wrong key). Body per `enum_values` (`ufield.py:65-85`):
        /// `[None][Next][Skip][count][value_name]*count`.
        pub(super) fn add_enum(&mut self, enum_name: &str, outer: i32, values: &[&str]) -> i64 {
            self.add_enum_ex(enum_name, outer, values, 0)
        }

        /// Full-featured `add_enum` -- adds a real `Next` field, needed when a struct/class's own
        /// `Children`/`Next` chain has a NON-PROPERTY sibling (a real corpus shape, round 15's
        /// review: `Core.Scale`'s own chain is `ESheerAxis (Enum) -> Scale -> SheerRate ->
        /// SheerAxis`, the enum sitting FIRST, before any real property -- see Step 5.65's own new
        /// test). `next_ref` is this export's own `Next` (0 = chain ends here, matching plain
        /// `add_enum`'s behavior).
        pub(super) fn add_enum_ex(&mut self, enum_name: &str, outer: i32, values: &[&str],
            next_ref: i64) -> i64 {
            let nm = self.name(enum_name);
            let mut body = encode_compact_index(0);           // None
            // The two fields between None and count are BOTH discarded by `enum_values`'s own
            // decode (it just skips two compacts before `count`), so their ORDER is invisible to
            // that decoder -- but it is NOT invisible to `field_next`'s GENERIC Children/Next walk
            // (Step 5.65's own real corpus finding: a struct's Children chain can hold a
            // non-property sibling like an Enum, and `field_next` reads ANY UField export the
            // same way -- consume the tagged-prop header (here, the leading "None"), discard the
            // NEXT compact as `_sup`, then return the ONE AFTER THAT as `next`). An earlier draft
            // of this fixture wrote `next_ref` in the FIRST slot (discarded as `_sup`) and 0 in
            // the second (returned as `next`), which made every splice-into-a-real-chain test pass
            // vacuously (the chain always looked like it terminated right after the enum) --
            // empirically corrected against `uprops/test_uprops.py`'s own
            // `test_a_struct_class_default_renders_from_the_committed_packages` (a REAL committed
            // package's `Engine.Brush.MainScale`, whose own `Scale` struct has this exact
            // ESheerAxis-then-members shape and decodes correctly against unmodified production
            // code): `next_ref` belongs in the SECOND slot.
            body.extend_from_slice(&encode_compact_index(0));        // discarded by field_next as `_sup`
            body.extend_from_slice(&encode_compact_index(next_ref)); // returned by field_next as `next`
            body.extend_from_slice(&encode_compact_index(values.len() as i64)); // count
            for v in values {
                let idx = self.name(v);
                body.extend_from_slice(&encode_compact_index(idx));
            }
            // cls MUST resolve to "Enum" -- enum_values (ufield.py:73) checks this exactly and
            // silently returns [] (not an error) if it doesn't, which would make an enum
            // canonicalization test pass vacuously instead of failing loudly.
            let enum_cls = self.import_type("Enum");
            self.exports.push((enum_cls, 0, outer, nm, 0, body));
            self.exports.len() as i64
        }

        /// Assembles the final package bytes. Two passes: first compute every table's encoded
        /// byte length (names, imports) and each export's OWN "head" length (cls/sup/outer/nm/
        /// flags/ssize -- everything except soff, which depends on its body's length, itself
        /// independent of layout). Then a GLOBAL fixed-point loop solves EVERY export's `soff`
        /// simultaneously each iteration (not one-at-a-time in declaration order -- multiple
        /// exports' own soff-compact-index WIDTHS can all affect the shared export-table length
        /// at once, so each iteration recomputes the whole table length from the PREVIOUS
        /// iteration's widths, then re-derives every soff from that one consistent length; this
        /// converges the same way round 3's single-export version did, just over N unknowns
        /// instead of one).
        pub(super) fn build(&self) -> Vec<u8> {
            let mut names_blob = Vec::new();
            for n in &self.names {
                names_blob.extend_from_slice(&encode_compact_index(n.len() as i64));
                names_blob.extend_from_slice(n.as_bytes());
                names_blob.extend_from_slice(&0u32.to_le_bytes());
            }
            let mut imports_blob = Vec::new();
            for (cp, cn, pi, on) in &self.imports {
                imports_blob.extend_from_slice(&encode_compact_index(*cp));
                imports_blob.extend_from_slice(&encode_compact_index(*cn));
                imports_blob.extend_from_slice(&pi.to_le_bytes());
                imports_blob.extend_from_slice(&encode_compact_index(*on));
            }

            let name_offset = HEADER_FIXED + 16;
            let import_offset = name_offset + names_blob.len();
            let export_offset = import_offset + imports_blob.len();

            // Pass 1: each export's HEAD (cls/sup/outer/nm/flags/ssize -- everything except soff)
            // has a fixed encoded length given its own field values, independent of layout.
            struct ExportPlan { head: Vec<u8>, body: Vec<u8> }
            let plans: Vec<ExportPlan> = self.exports.iter().map(|(cls, sup, outer, nm, flags, body)| {
                let mut head = encode_compact_index(*cls);
                head.extend_from_slice(&encode_compact_index(*sup));
                head.extend_from_slice(&outer.to_le_bytes());
                head.extend_from_slice(&encode_compact_index(*nm));
                head.extend_from_slice(&flags.to_le_bytes());
                head.extend_from_slice(&encode_compact_index(body.len() as i64)); // ssize
                ExportPlan { head, body: body.clone() }
            }).collect();
            let export_table_head_len: usize = plans.iter().map(|p| p.head.len()).sum();

            // Pass 2: solve ALL exports' soff together via a global fixed point (see the method
            // doc above) -- each iteration recomputes the whole export-table length from the
            // PREVIOUS iteration's widths, then re-derives every soff from that one shared length.
            let mut soff_widths = vec![1usize; plans.len()];
            let mut export_blobs: Vec<Vec<u8>> = Vec::new();
            let mut converged = false;
            for _ in 0..8 {   // widths only grow (1->2->3->4->5 bytes at fixed magnitude
                                // thresholds), so this converges in at most a handful of
                                // iterations for any realistic fixture; fail loudly instead of
                                // hanging cargo test if that assumption is ever wrong.
                let export_table_len: usize = plans.iter().zip(&soff_widths)
                    .map(|(p, w)| p.head.len() + *w).sum();  // `*w` -- `.zip(&soff_widths)` yields
                                                               // `&usize`, `usize + &usize` doesn't
                                                               // compile without the deref.
                let mut body_offset = export_offset + export_table_len;
                let mut new_blobs = Vec::new();
                let mut new_widths = Vec::new();
                for p in &plans {
                    let soff_bytes = encode_compact_index(body_offset as i64);
                    new_widths.push(soff_bytes.len());
                    let mut blob = p.head.clone();
                    blob.extend_from_slice(&soff_bytes);
                    new_blobs.push(blob);
                    body_offset += p.body.len();
                }
                if new_widths == soff_widths { export_blobs = new_blobs; converged = true; break; }
                soff_widths = new_widths;
            }
            assert!(converged, "fixture soff fixed point did not converge -- fixture too large \
                     or a real bug; extend the iteration cap only after confirming which");

            let mut buf = vec![0u8; name_offset];
            buf[0..4].copy_from_slice(&MAGIC.to_le_bytes());
            buf[4..8].copy_from_slice(&69u32.to_le_bytes());
            buf[8..12].copy_from_slice(&0u32.to_le_bytes());
            buf[12..16].copy_from_slice(&(self.names.len() as u32).to_le_bytes());
            buf[16..20].copy_from_slice(&(name_offset as u32).to_le_bytes());
            buf[20..24].copy_from_slice(&(self.exports.len() as u32).to_le_bytes());
            buf[24..28].copy_from_slice(&(export_offset as u32).to_le_bytes());
            buf[28..32].copy_from_slice(&(self.imports.len() as u32).to_le_bytes());
            buf[32..36].copy_from_slice(&(import_offset as u32).to_le_bytes());
            buf.extend_from_slice(&names_blob);
            buf.extend_from_slice(&imports_blob);
            for blob in &export_blobs { buf.extend_from_slice(blob); }
            // `parse_package` only reads `soff` when `ssize > 0` (package_read.rs:353-357); this
            // builder always emits a `soff` compact regardless, which is only correct as long as
            // every export built here has a non-empty body. Every `add_class`/`add_property`/
            // `add_struct_with_members`/`add_enum` call in this plan does produce one (a class's
            // own body header alone is dozens of bytes; a property/struct/enum body is never
            // empty either) -- pin that invariant rather than silently relying on it forever.
            assert!(plans.iter().all(|p| !p.body.is_empty()),
                "FixtureBuilder assumes every export has a non-empty body (soff is always emitted); \
                 an empty-body export needs its export entry built WITHOUT a soff field instead");
            for p in &plans { buf.extend_from_slice(&p.body); }
            buf
        }
    }

    /// Real FArrayIndex encoder (`package_read::read_array_index`'s exact inverse,
    /// `package_read.rs:61-80`): single byte if `0 <= idx < 128`; this fixture builder only
    /// ever needs small indices (array defaults in a test are a handful of elements, never near
    /// 128), so only the single-byte form is implemented -- panics if `idx` doesn't fit, which is
    /// a deliberate signal to extend this helper rather than silently emit a wrong encoding.
    pub(super) fn encode_array_index(idx: i64) -> Vec<u8> {
        assert!((0..128).contains(&idx), "encode_array_index: {idx} needs the 2-or-4-byte form, \
                 not implemented -- extend this helper if a test genuinely needs it");
        vec![idx as u8]
    }

    /// Hand-encodes one non-bool, non-struct property VALUE tag (int/byte/name/etc, for a
    /// class's own default-tag block or an actor's stated props), matching `read_property_tags`'s
    /// format exactly (`package_read.rs:496-547`). Uses size_code=7 (explicit u32 size,
    /// `package_read.rs:522`) for EVERY value regardless of length -- size_code=2 means "always
    /// exactly 4 bytes, no size field at all" and was a real bug in an earlier draft of this
    /// fixture builder. `name_idx`/`ptype` per the real UE1 property-type-byte values (1=byte,
    /// 2=int, 3=bool [`package_read.rs`'s own `PT_BOOL`], 4=float, 5=object, 6=name, 7=str
    /// [legacy form, `PT_STR_LEGACY`, `upackage.py:297`; `render_default_tag`, `values.py:454-458`,
    /// handles it], 8=class, 9=array, 10=struct [`PT_STRUCT`], 11=vector, 12=rotator, 13=str
    /// [current form — round 12's review confirmed real default tags across the whole corpus use
    /// only `{1,2,3,4,5,6,9,10,13}`; 11/12 exist as VALID ptypes per `package_read.rs` but no
    /// actual default-tag in this corpus uses them, so they're untested but not fictional]) —
    /// ONLY `PT_BOOL`/`PT_STRUCT` are named constants in `package_read.rs` today; the others are
    /// plain integers, confirmed against that file's
    /// own `missing_none_terminator_is_an_error` test comment ("an int tag (ptype 2, ...)").
    /// `array_index`: `Some(i)` sets bit7 and emits `encode_array_index(i)` AFTER the size field
    /// and BEFORE the value bytes (`package_read.rs:531-543`'s exact read order) -- REQUIRED for
    /// Step 11's positional array-default test (each element of a static array property is its
    /// own tag, distinguished ONLY by this field; `None` here means index 0 implicitly, matching
    /// a non-array property or an array's own element 0).
    pub(super) fn encode_fixed_tag(name_idx: i64, ptype: u8, array_index: Option<i64>,
                                     value: &[u8]) -> Vec<u8> {
        let mut out = encode_compact_index(name_idx);
        let bit7 = if array_index.is_some() { 0x80 } else { 0 };
        out.push(bit7 | (7 << 4) | ptype);                   // info byte: size_code=7
        out.extend_from_slice(&(value.len() as u32).to_le_bytes()); // explicit u32 size
        if let Some(i) = array_index { out.extend_from_slice(&encode_array_index(i)); }
        out.extend_from_slice(value);
        out
    }

    /// Hand-encodes one `BoolProperty` default/stated-value tag (`PT_BOOL = 3`) — a SEVENTH
    /// missing subsystem round 14's review found: `encode_fixed_tag` above is explicitly
    /// "non-bool, non-struct" and NO bool-tag builder existed, despite `PT_BOOL` being 37% of all
    /// real default tags measured across the golden 30's own Super chains (more common than every
    /// other ptype combined). **`PT_BOOL`'s wire form is NOT `encode_fixed_tag`'s** — the reader
    /// (`package_read.rs:524-529`) takes the branch on `ptype == PT_BOOL` BEFORE ever reading
    /// `array_index` or any value bytes: `bit7` of the info byte IS the bool's value itself, and
    /// NO payload bytes follow at all (`raw: Vec::new()`, `bool_value: Some(bit7)`) — calling
    /// `encode_fixed_tag(name_idx, 3, ..., &[])` would be wrong even with an empty value slice,
    /// since that still sets `bit7` to mean "array_index follows" and (for a non-empty
    /// `array_index`) would corrupt the value read as a real array index rather than a bool.
    /// **Known, confirmed real limitation (not fixed here, since no golden-30 case needs it):**
    /// because `bit7` is repurposed as the bool VALUE for this ptype, a bool tag has no way to
    /// carry an array index the way every other ptype's tag does (`package_read.rs`'s own
    /// `RawPropertyTag.array_index` is always `0` for a `PT_BOOL` tag) — a static array of
    /// `BoolProperty` with more than one element cannot be represented as distinct positional tags
    /// this way; this port does not need to solve that (no such case exists in the golden 30) but
    /// must not silently pretend it works either.
    pub(super) fn encode_bool_tag(name_idx: i64, value: bool) -> Vec<u8> {
        let mut out = encode_compact_index(name_idx);
        let bit7 = if value { 0x80 } else { 0 };
        out.push(bit7 | (7 << 4) | 3);                        // info byte: size_code=7 (unused), ptype=PT_BOOL
        out.extend_from_slice(&0u32.to_le_bytes());           // size field is read but never consumed for bool
        out
    }

    pub(super) fn none_terminator(none_name_idx: i64) -> Vec<u8> {
        encode_compact_index(none_name_idx)
    }

    /// One struct member ELEMENT's binary VALUE, for `encode_struct_value_bin` below -- per-kind
    /// wire forms exactly matching `_decode_struct_bin_at` (`uprops/values.py:142-203`) and this
    /// project's own RE doc (`dev/docs/unrealed/class-schema.md:154-160`): Int/Float are 4 raw
    /// little-endian bytes, Byte is 1 RAW ORDINAL byte regardless of whether the member has an
    /// enum (the wire format itself is always a single byte, per the RE doc -- this is NOT a
    /// claim about how `resolve_class` should RENDER an enum-typed byte in its own resolved
    /// output; Step 8's own `SheerAxis` test still requires the canonicalized ENUM NAME in that
    /// separate, later step, they are not the same thing), Struct recurses (its own member-wise
    /// binary, INLINE -- no length prefix, no terminator, nothing tag-shaped at all), Object is a
    /// plain compact-index object ref (needed by Step 6's excluded-member test — an `ObjectProperty`
    /// struct member's binary form is just this one compact index, no other framing), Name is a
    /// plain compact-index name-table ref (`_decode_struct_bin_at`'s `NameProperty` branch,
    /// `values.py:182-185` — needed for a `Name[N]`-typed member, e.g. the parent spec's own
    /// `sIconInfo.DamageType: Name[3]` worked example). **A member declared with `array_dim > 1`
    /// is represented by N CONSECUTIVE entries of the SAME variant in the `members` slice below —
    /// there is no separate "repeat" wrapper; `_decode_struct_bin_at` itself just loops
    /// `range(m.array_dim)` per member, emitting each element's own value back-to-back with no
    /// framing between elements** (`values.py:161`). `Bool`/`Str` variants added round 14's review
    /// (an EIGHTH missing subsystem finding): both occur as real corpus struct members (e.g.
    /// `Core.Color`'s siblings and several `Engine`-package structs carry a `BoolProperty` member;
    /// `StrProperty` struct members appear too) and `_decode_struct_bin_at` has real branches for
    /// both (`values.py:189-193` bool: exactly one byte, `0`/`1`, no compact-index framing at all
    /// — distinct from the TOP-LEVEL tag's `PT_BOOL` bit7-as-value trick, this is a plain byte;
    /// `values.py:186-188` str: an in-struct FString, same wire form as `read_fstring`
    /// (`package_read.rs:49`) — compact byte length INCLUDING the terminating NUL, then that many
    /// latin-1 bytes with the NUL as the last one).
    pub(super) enum StructMemberValue<'a> {
        Int(i32),
        Float(f32),
        Byte(u8),
        Bool(bool),
        Str(&'a str),
        Object(i64),
        Name(i64),
        Struct(&'a [StructMemberValue<'a>]),
    }

    /// Encodes a struct default's VALUE as member-wise binary, in Children-chain DECLARATION
    /// order (super-struct members first, per `class-schema.md:158-160`) -- NOT a tagged-property
    /// list. There are no name indices, info bytes, or a `"None"` terminator anywhere inside this
    /// blob; it is a flat concatenation of each member ELEMENT's own raw value bytes, one after
    /// another, in the SAME order `members` are declared in `add_struct_with_members`'s own member
    /// list for this struct — for an `array_dim > 1` member, list its `array_dim` elements as that
    /// many CONSECUTIVE entries here (see `StructMemberValue`'s own doc) — get this order or count
    /// wrong and the value silently misattributes to the wrong member instead of erroring, there
    /// is no self-describing structure to catch it.
    pub(super) fn encode_struct_value_bin(members: &[StructMemberValue]) -> Vec<u8> {
        let mut out = Vec::new();
        for m in members {
            match m {
                StructMemberValue::Int(v) => out.extend_from_slice(&v.to_le_bytes()),
                StructMemberValue::Float(v) => out.extend_from_slice(&v.to_le_bytes()),
                StructMemberValue::Byte(v) => out.push(*v),
                StructMemberValue::Bool(v) => out.push(if *v { 1 } else { 0 }),
                StructMemberValue::Str(s) => {
                    let mut bytes = s.as_bytes().to_vec();
                    bytes.push(0); // terminating NUL, counted in the length
                    out.extend_from_slice(&encode_compact_index(bytes.len() as i64));
                    out.extend_from_slice(&bytes);
                }
                StructMemberValue::Object(v) => out.extend_from_slice(&encode_compact_index(*v)),
                StructMemberValue::Name(v) => out.extend_from_slice(&encode_compact_index(*v)),
                StructMemberValue::Struct(inner) => out.extend_from_slice(&encode_struct_value_bin(inner)),
            }
        }
        out
    }

    /// Hand-encodes one `StructProperty` default TAG (`PT_STRUCT = 10`) -- `encode_fixed_tag`
    /// deliberately excludes this ptype (its own doc says "non-bool, non-struct") because
    /// `read_property_tags` reads an EXTRA `struct_name` compact index between the info byte and
    /// the size field for PT_STRUCT only (`package_read.rs:513-517`), which no other ptype has.
    /// `value_bin` is the struct's own VALUE, built by `encode_struct_value_bin` above -- member-
    /// wise BINARY, NOT a nested tagged-property list (an earlier draft of this fixture builder
    /// wrongly claimed the latter; `read_property_tags` captures whatever bytes are here as `raw`
    /// without interpreting them at all, so this function's own correctness matters for whatever
    /// Task 4's Rust `resolve_class` later decodes those raw bytes as — get the wire format
    /// wrong here and both sides would agree with each other while diverging from every real
    /// `.u` file).
    pub(super) fn encode_struct_tag(name_idx: i64, struct_name_idx: i64, array_index: Option<i64>,
                                      value_bin: &[u8]) -> Vec<u8> {
        let mut out = encode_compact_index(name_idx);
        let bit7 = if array_index.is_some() { 0x80 } else { 0 };
        out.push(bit7 | (7 << 4) | 10);                        // info byte: size_code=7, ptype=PT_STRUCT
        out.extend_from_slice(&encode_compact_index(struct_name_idx)); // struct_name -- ONLY for PT_STRUCT
        out.extend_from_slice(&(value_bin.len() as u32).to_le_bytes()); // explicit u32 size
        if let Some(i) = array_index { out.extend_from_slice(&encode_array_index(i)); }
        out.extend_from_slice(value_bin);
        out
    }

    #[test]
    fn fixture_builder_round_trips_through_the_real_decoder() {
        // Throwaway test proving the builder itself is correct BEFORE any resolve_class test
        // blames a decode failure on resolve_class's own logic.
        let mut fb = FixtureBuilder::new();
        let int_prop_name = fb.name("IntProp");
        let mut tag_bytes = encode_fixed_tag(int_prop_name, 2, None, &42i32.to_le_bytes()); // ptype 2 = int
        tag_bytes.extend_from_slice(&none_terminator(0)); // 0 = "None"
        fb.add_class("TestClass", 0, &tag_bytes);
        let buf = fb.build();
        let pkg = crate::package_read::parse_package(&buf).unwrap();
        assert_eq!(pkg.exports.len(), 1);
        let e = &pkg.exports[0];
        let names: Vec<String> = pkg.names.iter().map(|(n, _)| n.clone()).collect();
        // Tags sit AFTER the UClass body header, NOT at soff directly -- round 4's review (C1)
        // found a previous draft's round-trip test read at `soff` and decoded byte 0 (part of the
        // body header) as a bogus "None" tag instead of the real tag block. The header's length
        // is NOT a fixed constant (round 10's review, C1) -- compute it the same way `add_class`
        // did, from the SAME empty script_bin/deps/pkg_imports this call used.
        let tag_start = e.soff as usize + class_body_header(&[], 0, &[], &[], 0, 0).len();
        let (tags, end) = crate::package_read::read_property_tags(
            &buf, tag_start, (e.soff + e.ssize) as usize, &names
        ).unwrap();
        assert_eq!(end, (e.soff + e.ssize) as usize);
        assert_eq!(tags.len(), 1);
        assert_eq!(tags[0].name, "IntProp");
        assert_eq!(tags[0].raw, 42i32.to_le_bytes());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serializes_scalar_enum_struct_array_leaves_matching_parent_spec_shape() {
        let mut types = BTreeMap::new();
        types.insert("Core.Rotator".to_string(), TypeShape::Struct {
            members: vec![
                TypeMember { name: "Pitch".into(), kind: MemberKind::Scalar(ScalarKind::Int) },
                TypeMember { name: "Yaw".into(), kind: MemberKind::Scalar(ScalarKind::Int) },
                TypeMember { name: "Roll".into(), kind: MemberKind::Scalar(ScalarKind::Int) },
            ],
        });
        let class = ClassResolution {
            class: ResolvedClass { props: vec![ResolvedProp::Struct {
                name: "RotationRate".into(), category: "Movement".into(),
                struct_type: "Core.Rotator".into(),
                default_value: DefaultValue::Struct(BTreeMap::from([
                    ("Pitch".to_string(), DefaultValue::Scalar("4096".into())),
                    ("Yaw".to_string(), DefaultValue::Scalar("30000".into())),
                    ("Roll".to_string(), DefaultValue::Scalar("3072".into())),
                ])),
            }] },
            types,
        };
        let json: serde_json::Value = serde_json::from_str(&serde_json::to_string(&class).unwrap()).unwrap();
        // Matches the parent spec's own worked example, spec.md's resolve_class("DeusEx.Karkian", ...) fence
        assert_eq!(json["class"]["props"][0]["kind"], "struct");
        assert_eq!(json["class"]["props"][0]["struct_type"], "Core.Rotator");
        assert_eq!(json["class"]["props"][0]["default_value"]["Pitch"], "4096");
        assert_eq!(json["types"]["Core.Rotator"]["kind"], "struct");
        assert_eq!(json["types"]["Core.Rotator"]["members"][0]["name"], "Pitch");
        assert!(json["types"]["Core.Rotator"].get("values").is_none()); // struct never emits "values"
    }

    // The parent spec's own worked example (DeusEx.DamageHUDDisplay.sIconInfo's DamageType:
    // Name[3]) -- the test that would have caught the double-nesting bug (a plain derive on
    // `TypeMember` nests `MemberKind`'s own object under a "kind" key instead of flattening).
    #[test]
    fn type_member_scalar_array_is_flat_not_nested() {
        let member = TypeMember {
            name: "DamageType".into(),
            kind: MemberKind::ScalarArray { array_dim: 3, kind: ScalarKind::Name },
        };
        let json: serde_json::Value =
            serde_json::from_str(&serde_json::to_string(&member).unwrap()).unwrap();
        assert_eq!(json["kind"], "name");
        assert_eq!(json["array_dim"], 3);
        assert_eq!(json["name"], "DamageType");
        assert!(json.get("element_kind").is_none());
    }

    // `ResolvedProp::Scalar` -- the brief's own single most error-prone shape: its `kind:
    // ScalarKind` field collides with the outer "kind" discriminant, which is exactly why a plain
    // derive can't produce this and a manual impl is needed. Left completely unpinned until now.
    #[test]
    fn resolved_prop_scalar_kind_is_the_scalar_kind_not_a_wrapper() {
        let prop = ResolvedProp::Scalar {
            name: "Health".into(), category: "Pawn".into(), kind: ScalarKind::Int,
            default_value: "100".into(),
        };
        let json = serde_json::to_value(&prop).unwrap();
        assert_eq!(json["kind"], "int");
        assert_eq!(json["name"], "Health");
        assert_eq!(json["category"], "Pawn");
        assert_eq!(json["default_value"], "100");
        assert!(json.get("enum_type").is_none());
        assert!(json.get("struct_type").is_none());
    }

    #[test]
    fn resolved_prop_enum_emits_enum_type() {
        let prop = ResolvedProp::Enum {
            name: "Physics".into(), category: "Movement".into(),
            enum_type: "Engine.EPhysics".into(), default_value: "PHYS_Walking".into(),
        };
        let json = serde_json::to_value(&prop).unwrap();
        assert_eq!(json["kind"], "enum");
        assert_eq!(json["enum_type"], "Engine.EPhysics");
        assert_eq!(json["default_value"], "PHYS_Walking");
    }

    // `TypeShape::Enum{values}` -- the other half of the members/values XOR; only Struct was ever
    // exercised before.
    #[test]
    fn type_shape_enum_emits_values_never_members() {
        let shape = TypeShape::Enum { values: vec!["PHYS_Walking".into(), "PHYS_Falling".into()] };
        let json = serde_json::to_value(&shape).unwrap();
        assert_eq!(json["kind"], "enum");
        assert_eq!(json["values"][0], "PHYS_Walking");
        assert_eq!(json["values"][1], "PHYS_Falling");
        assert!(json.get("members").is_none());
    }

    // All six `ScalarKind` wire strings (spec §2) -- Int/Name were already covered incidentally
    // above; this pins the remaining four so a typo in any arm is caught.
    #[test]
    fn scalar_kind_covers_all_six_wire_strings() {
        let cases = [
            (ScalarKind::Float, "float"),
            (ScalarKind::Int, "int"),
            (ScalarKind::Bool, "bool"),
            (ScalarKind::Byte, "byte"),
            (ScalarKind::Name, "name"),
            (ScalarKind::StringKind, "string"),
        ];
        for (kind, expected) in cases {
            assert_eq!(serde_json::to_value(kind).unwrap(), serde_json::json!(expected));
        }
    }

    #[test]
    fn default_value_serializes_untagged_bare_string_object_array() {
        let scalar = DefaultValue::Scalar("100".into());
        assert_eq!(serde_json::to_value(&scalar).unwrap(), serde_json::json!("100"));

        let obj = DefaultValue::Struct(BTreeMap::from([
            ("X".to_string(), DefaultValue::Scalar("1".into())),
        ]));
        assert_eq!(serde_json::to_value(&obj).unwrap(), serde_json::json!({"X": "1"}));

        let arr = DefaultValue::Array(vec![DefaultValue::Scalar("1".into()), DefaultValue::Scalar("2".into())]);
        assert_eq!(serde_json::to_value(&arr).unwrap(), serde_json::json!(["1", "2"]));
    }

    // Top-level `ResolvedProp::Array` leaf: element_kind (scalar) XOR element_type (struct/enum).
    #[test]
    fn resolved_prop_array_element_kind_xor_element_type() {
        let scalar_leaf = ResolvedProp::Array {
            name: "Foo".into(), category: "Cat".into(), array_dim: 2,
            element: ArrayElementKind::Scalar(ScalarKind::Int),
            default_value: vec![DefaultValue::Scalar("0".into())],
        };
        let json = serde_json::to_value(&scalar_leaf).unwrap();
        assert_eq!(json["kind"], "array");
        assert_eq!(json["element_kind"], "int");
        assert!(json.get("element_type").is_none());

        let struct_leaf = ResolvedProp::Array {
            name: "Bar".into(), category: "Cat".into(), array_dim: 1,
            element: ArrayElementKind::Struct("Core.Vector".into()),
            default_value: vec![],
        };
        let json = serde_json::to_value(&struct_leaf).unwrap();
        assert_eq!(json["element_type"], "Core.Vector");
        assert!(json.get("element_kind").is_none());

        let enum_leaf = ResolvedProp::Array {
            name: "Baz".into(), category: "Cat".into(), array_dim: 1,
            element: ArrayElementKind::Enum("Engine.EPhysics".into()),
            default_value: vec![],
        };
        let json = serde_json::to_value(&enum_leaf).unwrap();
        assert_eq!(json["element_type"], "Engine.EPhysics");
        assert!(json.get("element_kind").is_none());
    }

    // `TypeMember`'s own `MemberKind::StructArray`/`EnumArray` -- the asymmetric shape (distinct
    // from `ResolvedProp::Array` above): "kind":"array" + "element_type", same field name as the
    // top-level leaf's struct/enum case, but reached via a different variant shape entirely.
    #[test]
    fn type_member_struct_array_and_enum_array_use_element_type() {
        let struct_array = TypeMember {
            name: "Slots".into(),
            kind: MemberKind::StructArray { array_dim: 4, struct_type: "Core.Vector".into() },
        };
        let json = serde_json::to_value(&struct_array).unwrap();
        assert_eq!(json["kind"], "array");
        assert_eq!(json["array_dim"], 4);
        assert_eq!(json["element_type"], "Core.Vector");

        let enum_array = TypeMember {
            name: "States".into(),
            kind: MemberKind::EnumArray { array_dim: 2, enum_type: "Engine.EPhysics".into() },
        };
        let json = serde_json::to_value(&enum_array).unwrap();
        assert_eq!(json["kind"], "array");
        assert_eq!(json["array_dim"], 2);
        assert_eq!(json["element_type"], "Engine.EPhysics");
    }

    #[test]
    fn actor_resolution_serializes_sparse_and_note() {
        let resolved = ActorResolution {
            sparse: BTreeMap::from([("Location.X".to_string(), "100".to_string())]),
            note: None,
        };
        let json = serde_json::to_value(&resolved).unwrap();
        assert_eq!(json["sparse"]["Location.X"], "100");
        assert_eq!(json["note"], serde_json::Value::Null);

        let degraded = ActorResolution { sparse: BTreeMap::new(), note: Some("schema unavailable".into()) };
        let json = serde_json::to_value(&degraded).unwrap();
        assert_eq!(json["note"], "schema unavailable");
    }

    #[test]
    fn resolve_error_display_names_the_offending_value() {
        assert_eq!(
            ResolveError::UnresolvableClass("DeusEx.Karkian".into()).to_string(),
            "class not found: DeusEx.Karkian"
        );
        assert_eq!(
            ResolveError::MissingPackage("DeusEx".into()).to_string(),
            "package not added: DeusEx"
        );
        assert_eq!(
            ResolveError::MalformedSchema { class: "DeusEx.Karkian".into(), reason: "bad tag".into() }
                .to_string(),
            "malformed schema for class DeusEx.Karkian: bad tag"
        );
        assert_eq!(
            ResolveError::MalformedPackage { name: "DeusEx.u".into(), reason: "truncated".into() }
                .to_string(),
            "malformed package DeusEx.u: truncated"
        );
    }

    #[test]
    fn add_package_is_idempotent_and_has_package_reflects_it() {
        let mut ctx = ResolutionContext::new();
        assert!(!ctx.has_package("Core"));
        let bytes = context_fixture::synthetic_package_with_imports(&[]);
        ctx.add_package("Core", bytes.clone()).unwrap();
        assert!(ctx.has_package("Core"));
        ctx.add_package("Core", bytes).unwrap();   // re-add is a cheap no-op, not an error
        assert!(ctx.has_package("Core"));
    }

    #[test]
    fn add_package_malformed_bytes_returns_malformed_package_error() {
        let mut ctx = ResolutionContext::new();
        let err = ctx.add_package("Bad", vec![0u8; 4]).unwrap_err();
        assert!(matches!(err, ResolveError::MalformedPackage { name, .. } if name == "Bad"));
    }

    #[test]
    fn package_imports_filters_to_class_struct_enum_and_property_type_imports() {
        let mut ctx = ResolutionContext::new();
        // A mix of Class/Struct/Texture/Mesh-typed import class-names -- assert the filter keeps
        // only Class/Struct/Enum/*Property imports, resolved to their OWNING package name via the
        // real outer-chain walk (context_fixture::synthetic_package_with_imports builds exactly this).
        let bytes = context_fixture::synthetic_package_with_imports(&[
            ("Class", "Engine"), ("Struct", "Engine"),
            ("Texture", "SomeTexturePackage"), ("Mesh", "SomeTexturePackage"),
        ]);
        ctx.add_package("DeusEx", bytes).unwrap();
        let imports = ctx.package_imports("DeusEx").unwrap();
        assert!(imports.contains(&"Engine".to_string()));
        assert!(!imports.contains(&"SomeTexturePackage".to_string()));
    }

    #[test]
    fn package_imports_on_unadded_package_returns_missing_package_error() {
        let ctx = ResolutionContext::new();
        assert!(matches!(ctx.package_imports("Nope").unwrap_err(), ResolveError::MissingPackage(n) if n == "Nope"));
    }

    #[test]
    fn a_failed_add_package_poisons_the_context_for_further_use() {
        let mut ctx = ResolutionContext::new();
        ctx.add_package("A", context_fixture::synthetic_package_with_imports(&[])).unwrap();
        assert!(ctx.has_package("A"));                          // genuinely true before poisoning
        let _ = ctx.add_package("B", vec![0u8; 4]);              // fails -- malformed, poisons ctx
        // A call that would otherwise succeed (querying an already-good package) now errors too --
        // this is what distinguishes "poisoned" from "not poisoned": an unpoisoned context would
        // still report has_package("A") == true here.
        assert!(ctx.package_imports("A").is_err());
        assert!(!ctx.has_package("A"));   // has_package degrades to false, not an error -- its own
                                            // signature (-> bool) has no error channel.
    }

    #[test]
    fn explicit_poison_call_has_the_same_effect_as_an_add_package_failure() {
        let mut ctx = ResolutionContext::new();
        ctx.add_package("A", context_fixture::synthetic_package_with_imports(&[])).unwrap();
        ctx.poison("simulated: caller's own pre-add_package resolution failed".to_string());
        assert!(!ctx.has_package("A"));
        assert!(ctx.package_imports("A").is_err());
    }

    #[test]
    fn a_fresh_context_is_not_poisoned() {
        let mut ctx = ResolutionContext::new();
        ctx.add_package("A", context_fixture::synthetic_package_with_imports(&[])).unwrap();
        assert!(ctx.package_imports("A").is_ok());   // control case: same call, no prior failure, succeeds
    }

    // --- Step 0.5: the UnrealScript bytecode walker (_walk_expr/_skip_script) ---

    // Test 1: a script blob of exactly one EndFunctionParms, mem=1.
    #[test]
    fn skip_script_walks_a_single_end_function_parms_token() {
        let names: Vec<String> = Vec::new();
        let buf = [0x16u8];
        let pos = skip_script(&buf, &names, 0, 1).unwrap();
        assert_eq!(pos, 1);
    }

    // Test 2: a real IntConst -- disk and in-memory sizes agree (a fixed-size operand).
    #[test]
    fn skip_script_int_const_disk_and_memory_sizes_agree() {
        let names: Vec<String> = Vec::new();
        let mut buf = vec![0x1Du8];
        buf.extend_from_slice(&42i32.to_le_bytes());
        let pos = skip_script(&buf, &names, 0, 5).unwrap();
        assert_eq!(pos, 5);
    }

    // Test 3: ObjectConst -- a compact-encoded ref whose on-disk width (1 byte) differs from its
    // in-memory size (4 bytes), the whole reason this walker exists. disk: opcode(1) + compact(1)
    // = 2 bytes; memory: opcode(1) + obj()'s own fixed 4 = 5 bytes.
    #[test]
    fn skip_script_object_const_disk_and_memory_diverge() {
        let names: Vec<String> = Vec::new();
        let mut buf = vec![0x20u8];
        buf.extend_from_slice(&fixture::encode_compact_index(5)); // 1-byte on disk
        let pos = skip_script(&buf, &names, 0, 5).unwrap();
        assert_eq!(pos, 2);
    }

    // Test 4: an unknown opcode errors, never panics.
    #[test]
    fn skip_script_unknown_opcode_errors_not_panics() {
        let names: Vec<String> = Vec::new();
        let buf = [0x35u8]; // deliberately unassigned in the real opcode table
        let err = skip_script(&buf, &names, 0, 1).unwrap_err();
        assert!(matches!(err, ResolveError::MalformedPackage { .. }));
    }

    // Test 4 (StringConst half): no NUL before the buffer's own end -- the 0x1F arm's NUL search
    // must use `buf.get(pos..)` (returns None/empty, handled) rather than a plain slice index
    // (`buf[pos..]`, which panics once `pos` runs past the buffer).
    #[test]
    fn skip_script_string_const_without_terminator_errors_not_panics() {
        let names: Vec<String> = Vec::new();
        let buf = [0x1Fu8, b'a', b'b']; // no NUL terminator anywhere in the buffer
        let err = skip_script(&buf, &names, 0, 3).unwrap_err();
        assert!(matches!(err, ResolveError::MalformedPackage { .. }));
    }

    // Test 5: _skip_script's OWN desync check -- a declared script_size that doesn't match what
    // the walk actually consumed. Uses the same ObjectConst divergence as Test 3 (mem=5) but
    // declares script_size=3, so the walk overshoots the declared size in one step (no buffer
    // overrun involved) -- isolates this check from a truncated-buffer error.
    #[test]
    fn skip_script_desync_between_declared_and_actual_size_errors() {
        let names: Vec<String> = Vec::new();
        let mut buf = vec![0x20u8];
        buf.extend_from_slice(&fixture::encode_compact_index(5));
        let err = skip_script(&buf, &names, 0, 3).unwrap_err();
        match err {
            ResolveError::MalformedPackage { reason, .. } => {
                assert!(reason.contains("script walk desync"), "reason: {reason}");
            }
            other => panic!("expected MalformedPackage, got {other:?}"),
        }
    }

    // --- Step 0.6: class_default_tags -- the full UClass-body walk ---

    // Test 1: deps: &[], pkg_imports: &[] (matching the Step 0 round-trip test) -- a drop-in
    // replacement for that test's own ad-hoc offset math, not a parallel implementation.
    #[test]
    fn class_default_tags_matches_the_round_trip_test_with_empty_deps_and_imports() {
        let mut fb = fixture::FixtureBuilder::new();
        let int_prop_name = fb.name("IntProp");
        let mut tag_bytes = fixture::encode_fixed_tag(int_prop_name, 2, None, &42i32.to_le_bytes());
        tag_bytes.extend_from_slice(&fixture::none_terminator(0));
        fb.add_class("TestClass", 0, &tag_bytes);
        let buf = fb.build();
        let pkg = crate::package_read::parse_package(&buf).unwrap();
        let names: Vec<String> = pkg.names.iter().map(|(n, _)| n.clone()).collect();
        let e = &pkg.exports[0];
        let tags = class_default_tags(&buf, &names, e.soff, e.ssize).unwrap();
        assert_eq!(tags.len(), 1);
        assert_eq!(tags[0].name, "IntProp");
        assert_eq!(tags[0].raw, 42i32.to_le_bytes());
    }

    // Test 2: ONE non-empty Dependencies entry and ONE non-empty PackageImports entry -- proving
    // the walk correctly skips real, non-zero-count TArrays (every fixture before this one used
    // &[]/&[], which 0% of real classes actually have).
    #[test]
    fn class_default_tags_skips_non_empty_dependencies_and_package_imports() {
        let mut fb = fixture::FixtureBuilder::new();
        let int_prop_name = fb.name("IntProp");
        let pkg_import_name = fb.name("SomePkgImportName");
        let mut tag_bytes = fixture::encode_fixed_tag(int_prop_name, 2, None, &7i32.to_le_bytes());
        tag_bytes.extend_from_slice(&fixture::none_terminator(0));
        fb.add_class_ex("TestClass2", 0, &[], 0,
            &[fixture::DependencyEntry { class_ref: 3, deep: 1, crc: 0 }],
            &[pkg_import_name], 0, 0, &tag_bytes);
        let buf = fb.build();
        let pkg = crate::package_read::parse_package(&buf).unwrap();
        let names: Vec<String> = pkg.names.iter().map(|(n, _)| n.clone()).collect();
        let e = &pkg.exports[0];
        let tags = class_default_tags(&buf, &names, e.soff, e.ssize).unwrap();
        assert_eq!(tags.len(), 1);
        assert_eq!(tags[0].name, "IntProp");
        assert_eq!(tags[0].raw, 7i32.to_le_bytes());
    }

    // Test 3: an intrinsic class (ssize <= 0) -- no attempt to read past a nonexistent body.
    #[test]
    fn class_default_tags_returns_empty_for_non_positive_ssize() {
        assert!(class_default_tags(&[], &[], 0, 0).unwrap().is_empty());
        assert!(class_default_tags(&[], &[], 0, -5).unwrap().is_empty());
    }

    // Test 4: class_default_tags' OWN consume-exactly check -- a real, correctly-built class body
    // but a wrong `ssize` (one byte too many, so the decode terminates BEFORE `end`, distinct
    // from _skip_script's own desync check, Step 0.5 Test 5).
    #[test]
    fn class_default_tags_errors_when_the_tag_block_does_not_land_exactly_at_end() {
        let mut fb = fixture::FixtureBuilder::new();
        let int_prop_name = fb.name("IntProp");
        let mut tag_bytes = fixture::encode_fixed_tag(int_prop_name, 2, None, &42i32.to_le_bytes());
        tag_bytes.extend_from_slice(&fixture::none_terminator(0));
        fb.add_class("TestClass", 0, &tag_bytes);
        let mut buf = fb.build();
        buf.push(0xAA); // padding so ssize+1 stays within the physical buffer
        let pkg = crate::package_read::parse_package(&buf).unwrap();
        let names: Vec<String> = pkg.names.iter().map(|(n, _)| n.clone()).collect();
        let e = &pkg.exports[0];
        let err = class_default_tags(&buf, &names, e.soff, e.ssize + 1).unwrap_err();
        match err {
            ResolveError::MalformedPackage { reason, .. } => {
                assert!(reason.contains("did not consume to body end"), "reason: {reason}");
            }
            other => panic!("expected MalformedPackage, got {other:?}"),
        }
    }

    // Test 5: a fully-realistic class -- every variable piece non-empty AT ONCE (a real divergent
    // script_bin/script_mem_size pair, non-empty deps/pkg_imports, and non-zero ClassWithin/
    // ClassConfigName), not just one at a time in isolation (round 12's review, I1/I3).
    #[test]
    fn class_default_tags_decodes_with_every_variable_piece_non_empty_at_once() {
        let mut fb = fixture::FixtureBuilder::new();
        let int_prop_name = fb.name("IntProp");
        let pkg_import_name = fb.name("SomePkgImportName");
        let class_within_name = fb.name("SomeWithinClass");
        let class_config_name = fb.name("SomeConfigName");
        let mut script_bin = vec![0x20u8];
        script_bin.extend_from_slice(&fixture::encode_compact_index(5)); // ObjectConst, disk 2 / mem 5
        let mut tag_bytes = fixture::encode_fixed_tag(int_prop_name, 2, None, &99i32.to_le_bytes());
        tag_bytes.extend_from_slice(&fixture::none_terminator(0));
        fb.add_class_ex("TestClass3", 0, &script_bin, 5,
            &[fixture::DependencyEntry { class_ref: 3, deep: 1, crc: 0 }],
            &[pkg_import_name], class_within_name, class_config_name, &tag_bytes);
        let buf = fb.build();
        let pkg = crate::package_read::parse_package(&buf).unwrap();
        let names: Vec<String> = pkg.names.iter().map(|(n, _)| n.clone()).collect();
        let e = &pkg.exports[0];
        let tags = class_default_tags(&buf, &names, e.soff, e.ssize).unwrap();
        assert_eq!(tags.len(), 1);
        assert_eq!(tags[0].name, "IntProp");
        assert_eq!(tags[0].raw, 99i32.to_le_bytes());
    }

    // --- Task 4 Steps 1-4.6: resolve_class ---

    fn prop_name(p: &ResolvedProp) -> &str {
        match p {
            ResolvedProp::Scalar { name, .. } => name,
            ResolvedProp::Enum { name, .. } => name,
            ResolvedProp::Struct { name, .. } => name,
            ResolvedProp::Array { name, .. } => name,
        }
    }

    fn prop_category<'a>(p: &'a ResolvedProp) -> &'a str {
        match p {
            ResolvedProp::Scalar { category, .. } => category,
            ResolvedProp::Enum { category, .. } => category,
            ResolvedProp::Struct { category, .. } => category,
            ResolvedProp::Array { category, .. } => category,
        }
    }

    fn prop_default_text(p: &ResolvedProp) -> &str {
        match p {
            ResolvedProp::Scalar { default_value, .. } => default_value,
            ResolvedProp::Enum { default_value, .. } => default_value,
            other => panic!("prop_default_text: not a scalar/enum prop: {}", prop_name(other)),
        }
    }

    fn prop_struct_default(p: &ResolvedProp) -> &DefaultValue {
        match p {
            ResolvedProp::Struct { default_value, .. } => default_value,
            other => panic!("prop_struct_default: not a struct prop: {}", prop_name(other)),
        }
    }

    // Step 1: cache-hit vs. cache-miss and the resolutions_performed counter.
    #[test]
    fn resolve_class_caches_after_first_resolution() {
        let mut fb = fixture::FixtureBuilder::new();
        fb.add_class("Simple", 0, &[]);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        assert_eq!(ctx.resolutions_performed(), 0);
        resolve_class("Pkg.Simple", &mut ctx).unwrap();
        assert_eq!(ctx.resolutions_performed(), 1);
        resolve_class("Pkg.Simple", &mut ctx).unwrap(); // cache hit -- no re-walk
        assert_eq!(ctx.resolutions_performed(), 1);
    }

    // Step 2/3: Super-chain merge -- child's own override wins on a case-folded name collision,
    // the parent's un-overridden prop is still inherited.
    #[test]
    fn resolve_class_merges_super_chain_child_overrides_parent() {
        let mut fb = fixture::FixtureBuilder::new();
        let parent_idx = fb.add_class("Parent", 0, &[]);
        fb.add_property("Health", "IntProperty", parent_idx, 1, "Movement", None);
        fb.add_property("Shield", "IntProperty", parent_idx, 1, "Movement", None);
        let child_idx = fb.add_class("Child", parent_idx, &[]);
        fb.add_property("Health", "IntProperty", child_idx, 1, "Combat", None); // override
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.Child", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert_eq!(names.iter().filter(|&&n| n == "Health").count(), 1, "no duplicate on collision");
        let health = res.class.props.iter().find(|p| prop_name(p) == "Health").unwrap();
        assert_eq!(prop_category(health), "Combat", "the child's own override wins");
        assert!(names.contains(&"Shield"), "the parent's un-overridden prop is still inherited");
    }

    // Step 3: cycle guard -- a class whose own `sup` points back at itself truncates the walk
    // silently (its own props still resolve once), never a crash or an Err.
    #[test]
    fn resolve_class_self_referential_super_truncates_without_error() {
        let mut fb = fixture::FixtureBuilder::new();
        let predicted = fb.next_export_index();
        let actual = fb.add_class("SelfLoop", predicted, &[]);
        assert_eq!(actual, predicted);
        fb.add_property("Foo", "IntProperty", actual, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.SelfLoop", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert_eq!(names, vec!["Foo"]);
    }

    // Step 4: class-defaults decode -- a sparse diff against the super, decoded root-to-leaf.
    #[test]
    fn resolve_class_defaults_decode_root_to_leaf() {
        let mut fb = fixture::FixtureBuilder::new();
        let speed_name = fb.name("Speed");
        let mut parent_tags = fixture::encode_fixed_tag(speed_name, 2, None, &10i32.to_le_bytes());
        parent_tags.extend_from_slice(&fixture::none_terminator(0));
        let parent_idx = fb.add_class("Parent", 0, &parent_tags);
        fb.add_property("Speed", "IntProperty", parent_idx, 1, "Uncategorized", None);

        let flag_name = fb.name("Flag");
        let mut child_tags = fixture::encode_bool_tag(flag_name, true);
        child_tags.extend_from_slice(&fixture::none_terminator(0));
        let child_idx = fb.add_class("Child", parent_idx, &child_tags);
        fb.add_property("Flag", "BoolProperty", child_idx, 1, "Uncategorized", None);

        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.Child", &mut ctx).unwrap();

        let speed = res.class.props.iter().find(|p| prop_name(p) == "Speed").unwrap();
        assert_eq!(prop_default_text(speed), "10", "inherited default, not restated by the child");
        let flag = res.class.props.iter().find(|p| prop_name(p) == "Flag").unwrap();
        assert_eq!(prop_default_text(flag), "True");
    }

    // Step 4: PT_BOOL needs its own fixture builder (encode_bool_tag) -- true and false both.
    #[test]
    fn resolve_class_bool_default_tag_renders_true_and_false() {
        for (value, expect) in [(true, "True"), (false, "False")] {
            let mut fb = fixture::FixtureBuilder::new();
            let name_idx = fb.name("bSomeFlag");
            let mut tags = fixture::encode_bool_tag(name_idx, value);
            tags.extend_from_slice(&fixture::none_terminator(0));
            let class_idx = fb.add_class("BoolTest", 0, &tags);
            fb.add_property("bSomeFlag", "BoolProperty", class_idx, 1, "Uncategorized", None);
            let buf = fb.build();
            let mut ctx = ResolutionContext::new();
            ctx.add_package("Pkg", buf).unwrap();
            let res = resolve_class("Pkg.BoolTest", &mut ctx).unwrap();
            let prop = res.class.props.iter().find(|p| prop_name(p) == "bSomeFlag").unwrap();
            assert_eq!(prop_default_text(prop), expect);
        }
    }

    // Step 4: an unsupported default value type (PT_ARRAY=9) makes resolve_class return
    // Err(MalformedSchema) naming the ptype -- schema-agnostic to exclusion: this fires even
    // though ArrayProperty is itself an excluded kind with no wire shape of its own.
    #[test]
    fn resolve_class_unsupported_default_ptype_errors_even_for_an_excluded_kind_entry() {
        let mut fb = fixture::FixtureBuilder::new();
        let int_name = fb.name("Speed");
        let mut tags = fixture::encode_fixed_tag(int_name, 2, None, &5i32.to_le_bytes());
        let bad_name = fb.name("SurfList");
        tags.extend_from_slice(&fixture::encode_fixed_tag(bad_name, 9, None, &0i32.to_le_bytes())); // ptype 9 = PT_ARRAY
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasBadDefault", 0, &tags);
        fb.add_property("Speed", "IntProperty", class_idx, 1, "Uncategorized", None);
        // A REAL declared excluded-kind property matching the tag's own name -- the brief's own
        // cited `Engine.Decal` corpus example (`SurfList`, an `ArrayProperty`) -- not just an
        // unmatched tag name. Proves the error fires for a tag whose OWN prop is excluded from
        // the wire shape, not merely for a name with no schema entry at all.
        fb.add_property("SurfList", "ArrayProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let err = resolve_class("Pkg.HasBadDefault", &mut ctx).unwrap_err();
        match err {
            ResolveError::MalformedSchema { reason, .. } => {
                assert!(reason.contains("unsupported default value type 9"), "reason: {reason}");
            }
            other => panic!("expected MalformedSchema, got {other:?}"),
        }
    }

    // Step 4.5 (1): a plain IntProperty with no declared default anywhere in the Super chain.
    #[test]
    fn zero_fallback_int_prop_with_no_declared_default_is_zero() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("NoDefaultsInt", 0, &[]);
        fb.add_property("Count", "IntProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.NoDefaultsInt", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Count").unwrap();
        assert_eq!(prop_default_text(prop), "0");
    }

    // Step 4.5 (2): same for BoolProperty.
    #[test]
    fn zero_fallback_bool_prop_with_no_declared_default_is_false() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("NoDefaultsBool", 0, &[]);
        fb.add_property("bFlag", "BoolProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.NoDefaultsBool", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "bFlag").unwrap();
        assert_eq!(prop_default_text(prop), "False");
    }

    // Step 4.5 (3): an enum-typed ByteProperty with no stated default -- the enum's OWN first
    // value name, never the literal "0".
    #[test]
    fn zero_fallback_enum_byte_prop_with_no_declared_default_is_enums_first_name() {
        let mut fb = fixture::FixtureBuilder::new();
        let enum_idx = fb.add_enum("ETestEnum", 0, &["FIRST", "SECOND"]);
        let class_idx = fb.add_class("NoDefaultsEnum", 0, &[]);
        fb.add_property("Mode", "ByteProperty", class_idx, 1, "Uncategorized", Some(enum_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.NoDefaultsEnum", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Mode").unwrap();
        assert_eq!(prop_default_text(prop), "FIRST", "the enum's own first value name, not \"0\"");
    }

    // Step 4.5 (4): a StructProperty with no stated default at all -- recurses per member using
    // each member's own zero rule, a member static array repeats the SAME zero value across every
    // element, and an excluded member's zero value is computed (so the walk doesn't break) but
    // OMITTED from the assembled map.
    #[test]
    fn zero_fallback_struct_prop_recurses_per_member_including_a_repeated_array_member() {
        let mut fb = fixture::FixtureBuilder::new();
        let struct_idx = fb.add_struct_with_members("ZeroStruct", 0, 0, &[
            ("Flags", "BoolProperty", 2, "Uncategorized", None),
            ("Icon", "ObjectProperty", 1, "Uncategorized", None), // excluded -- must be OMITTED
            ("Count", "IntProperty", 1, "Uncategorized", None),
        ]);
        let class_idx = fb.add_class("NoDefaultsStruct", 0, &[]);
        fb.add_property("Data", "StructProperty", class_idx, 1, "Uncategorized", Some(struct_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.NoDefaultsStruct", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Data").unwrap();
        let DefaultValue::Struct(map) = prop_struct_default(prop) else { panic!("expected a struct default") };
        assert_eq!(map.get("Flags"), Some(&DefaultValue::Array(vec![
            DefaultValue::Scalar("False".into()), DefaultValue::Scalar("False".into()),
        ])), "a member static array repeats the same zero value across every element");
        assert_eq!(map.get("Count"), Some(&DefaultValue::Scalar("0".into())));
        assert!(!map.contains_key("Icon"), "excluded member must not appear in the zero-fallback tree");
    }

    // Step 4.5 (5): the SEPARATE, hardcoded TYPED_FIELDS fallback table -- distinct from the
    // generic zero rule above (Scale fallback is "1", not the generic float-zero "0").
    #[test]
    fn typed_field_fallback_table_is_separate_from_the_generic_zero_rule() {
        assert_eq!(typed_field_fallback("Location.X"), "0");
        assert_eq!(typed_field_fallback("Location.Y"), "0");
        assert_eq!(typed_field_fallback("Location.Z"), "0");
        assert_eq!(typed_field_fallback("Scale.X"), "1");
        assert_eq!(typed_field_fallback("Scale.Y"), "1");
        assert_eq!(typed_field_fallback("Scale.Z"), "1");
        assert_eq!(typed_field_fallback("SheerRate"), "0");
        assert_eq!(typed_field_fallback("SheerAxis"), "SHEER_ZX");
    }

    // Step 4.6: Struct-kind default_value TREE assembly, built directly off the per-kind byte
    // reads -- an included Name[3] member keys under its OWN bare name to a 3-element
    // DefaultValue::Array (never (i)-suffixed keys), Bool/Str members render their own text, an
    // EXCLUDED ObjectProperty member interleaved between two included ones is absent from the map,
    // and the included member AFTER the excluded one still decodes correctly (proving its bytes
    // were consumed, not skipped -- the cursor stayed in sync).
    #[test]
    fn resolve_class_struct_default_tree_omits_excluded_member_but_still_consumes_its_bytes() {
        let mut fb = fixture::FixtureBuilder::new();
        let struct_idx = fb.add_struct_with_members("SIconInfoTest", 0, 0, &[
            ("DamageType", "NameProperty", 3, "Uncategorized", None),
            ("Icon", "ObjectProperty", 1, "Uncategorized", None), // excluded, interleaved
            ("bActive", "BoolProperty", 1, "Uncategorized", None),
            ("SomeText", "StrProperty", 1, "Uncategorized", None),
        ]);
        let fire = fb.name("Fire");
        let ice = fb.name("Ice");
        let poison = fb.name("Poison");
        let value_bin = fixture::encode_struct_value_bin(&[
            fixture::StructMemberValue::Name(fire),
            fixture::StructMemberValue::Name(ice),
            fixture::StructMemberValue::Name(poison),
            fixture::StructMemberValue::Object(0),
            fixture::StructMemberValue::Bool(true),
            fixture::StructMemberValue::Str("hello"),
        ]);
        let struct_name_idx = fb.name("SIconInfoTest");
        let icon_info_name = fb.name("IconInfo");
        let mut tags = fixture::encode_struct_tag(icon_info_name, struct_name_idx, None, &value_bin);
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasIcon", 0, &tags);
        fb.add_property("IconInfo", "StructProperty", class_idx, 1, "Uncategorized", Some(struct_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasIcon", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "IconInfo").unwrap();
        let DefaultValue::Struct(map) = prop_struct_default(prop) else { panic!("expected a struct default") };
        assert_eq!(map.get("DamageType"), Some(&DefaultValue::Array(vec![
            DefaultValue::Scalar("Fire".into()),
            DefaultValue::Scalar("Ice".into()),
            DefaultValue::Scalar("Poison".into()),
        ])), "Name[3] member: bare-name key, 3-element Array, no (i)-suffixed keys");
        assert!(!map.contains_key("Icon"), "excluded ObjectProperty member must be absent");
        assert_eq!(map.get("bActive"), Some(&DefaultValue::Scalar("True".into())));
        assert_eq!(map.get("SomeText"), Some(&DefaultValue::Scalar("hello".into())),
            "the included member AFTER the excluded one still decodes correctly");
    }

    // --- Step 5: (package, outer, name) identity keying ---

    // A hand-built same-name-different-outer collision (mirroring the real corpus's
    // `XAIParams`/`sUserInfo` cases): two structs both named "Dup", one top-level, one nested
    // inside a class -- their identity keys must differ.
    #[test]
    fn type_identity_key_distinguishes_same_name_different_outer() {
        let mut fb = fixture::FixtureBuilder::new();
        let container_idx = fb.add_class("Container", 0, &[]);
        let top_level = fb.add_struct_with_members("Dup", 0, 0, &[
            ("X", "IntProperty", 1, "Uncategorized", None),
        ]);
        let nested = fb.add_struct_with_members("Dup", container_idx as i32, 0, &[
            ("Y", "IntProperty", 1, "Uncategorized", None),
        ]);
        let buf = fb.build();
        let pkg = crate::package_read::parse_package(&buf).unwrap();
        let names: Vec<String> = pkg.names.iter().map(|(n, _)| n.clone()).collect();
        let top_key = type_identity_key(&pkg, &names, "Pkg", top_level).unwrap();
        let nested_key = type_identity_key(&pkg, &names, "Pkg", nested).unwrap();
        assert_ne!(top_key, nested_key, "same-named structs with different outers must be distinct");
        assert_eq!(top_key, "Pkg.Dup");
        assert_eq!(nested_key, "Pkg.Container.Dup");
    }

    // --- Step 5.5: `types` closure collection, including transitively-referenced types ---

    // A struct member (`Outer.Nested`) whose own type (`Inner`) is ALSO a struct -- both must
    // appear in `ClassResolution.types`, keyed once each, even though only `Outer` is directly
    // referenced by the class's own top-level prop.
    #[test]
    fn resolve_class_types_closure_includes_a_transitively_referenced_struct() {
        let mut fb = fixture::FixtureBuilder::new();
        let inner_idx = fb.add_struct_with_members("Inner", 0, 0, &[
            ("Val", "IntProperty", 1, "Uncategorized", None),
        ]);
        let outer_idx = fb.add_struct_with_members("Outer", 0, 0, &[
            ("Nested", "StructProperty", 1, "Uncategorized", Some(inner_idx)),
        ]);
        let class_idx = fb.add_class("HasOuter", 0, &[]);
        fb.add_property("Data", "StructProperty", class_idx, 1, "Uncategorized", Some(outer_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasOuter", &mut ctx).unwrap();
        assert!(res.types.contains_key("Pkg.Outer"), "the directly-referenced type");
        assert!(res.types.contains_key("Pkg.Inner"),
            "the TRANSITIVELY-referenced type, via Outer's own member -- keyed once even though \
             only Outer is a top-level prop");
        let TypeShape::Struct { members } = &res.types["Pkg.Outer"] else { panic!("expected a struct shape") };
        assert_eq!(members.len(), 1);
        match &members[0].kind {
            MemberKind::Struct { struct_type } => assert_eq!(struct_type, "Pkg.Inner"),
            other => panic!("expected a Struct member kind, got {other:?}"),
        }
    }

    // --- Step 5.6: struct super-chain member recursion ---

    // `Core.Plane extends Core.Vector` -- the super's members ([X,Y,Z]) must be prepended to the
    // struct's own ([W]), in order, in `types["<pkg>.Plane"].members`.
    #[test]
    fn struct_super_chain_prepends_supers_members_in_order() {
        let mut fb = fixture::FixtureBuilder::new();
        let vector_idx = fb.add_struct_with_members("Vector", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
            ("Y", "FloatProperty", 1, "Uncategorized", None),
            ("Z", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let plane_idx = fb.add_struct_with_members("Plane", 0, vector_idx, &[
            ("W", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let class_idx = fb.add_class("HasPlane", 0, &[]);
        fb.add_property("P", "StructProperty", class_idx, 1, "Uncategorized", Some(plane_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasPlane", &mut ctx).unwrap();
        let TypeShape::Struct { members } = &res.types["Pkg.Plane"] else { panic!("expected a struct shape") };
        let names: Vec<&str> = members.iter().map(|m| m.name.as_str()).collect();
        assert_eq!(names, vec!["X", "Y", "Z", "W"], "super's members first, in declaration order");
    }

    // Same shape, but asserting the BINARY value decodes correctly against the FULL 4-member
    // layout (16 bytes: 4 floats) -- skipping the recursion would desync against a decoder
    // expecting only 4 bytes (1 float), the exact failure mode Step 5.6 exists to prevent.
    #[test]
    fn struct_super_chain_default_value_decodes_all_inherited_members() {
        let mut fb = fixture::FixtureBuilder::new();
        let vector_idx = fb.add_struct_with_members("Vector", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
            ("Y", "FloatProperty", 1, "Uncategorized", None),
            ("Z", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let plane_idx = fb.add_struct_with_members("Plane", 0, vector_idx, &[
            ("W", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let value_bin = fixture::encode_struct_value_bin(&[
            fixture::StructMemberValue::Float(1.0),
            fixture::StructMemberValue::Float(2.0),
            fixture::StructMemberValue::Float(3.0),
            fixture::StructMemberValue::Float(4.0),
        ]);
        let plane_name_idx = fb.name("Plane");
        let prop_name_idx = fb.name("P");
        let mut tags = fixture::encode_struct_tag(prop_name_idx, plane_name_idx, None, &value_bin);
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasPlane2", 0, &tags);
        fb.add_property("P", "StructProperty", class_idx, 1, "Uncategorized", Some(plane_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasPlane2", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "P").unwrap();
        let DefaultValue::Struct(map) = prop_struct_default(prop) else { panic!("expected a struct default") };
        assert_eq!(map.get("X"), Some(&DefaultValue::Scalar("1".into())));
        assert_eq!(map.get("Y"), Some(&DefaultValue::Scalar("2".into())));
        assert_eq!(map.get("Z"), Some(&DefaultValue::Scalar("3".into())));
        assert_eq!(map.get("W"), Some(&DefaultValue::Scalar("4".into())));
    }

    // A cyclic super-struct reference (A.sup -> B, B.sup -> A) -- a two-hop mutual reference,
    // built with the SAME forward-prediction discipline `add_struct_with_members`'s own doc
    // establishes (struct A's `sup` must name struct B's index BEFORE B exists at all). Must
    // return a `ResolveError` rather than looping forever.
    #[test]
    fn struct_super_chain_cycle_errors_instead_of_looping_forever() {
        let mut fb = fixture::FixtureBuilder::new();
        const A_MEMBERS: usize = 1; // struct A's own member count, kept in sync with the member list below
        const B_MEMBERS: usize = 1; // struct B's own member count
        let a_start = fb.next_export_index(); // A's members are pushed starting here
        let predicted_b_idx = a_start + A_MEMBERS as i64 + 1 + B_MEMBERS as i64; // A's members, then
                                                                                    // A itself, then
                                                                                    // B's members,
                                                                                    // then B.
        let actual_a_idx = fb.add_struct_with_members("A", 0, predicted_b_idx, &[
            ("M", "FloatProperty", 1, "Uncategorized", None),
        ]);
        assert_eq!(actual_a_idx, a_start + A_MEMBERS as i64); // MUST hold before trusting predicted_b_idx
        let actual_b_idx = fb.add_struct_with_members("B", 0, actual_a_idx, &[ // B's sup is A's REAL,
            ("N", "FloatProperty", 1, "Uncategorized", None),                 // already-known index.
        ]);
        assert_eq!(actual_b_idx, predicted_b_idx); // the whole trick only works if BOTH asserts hold

        let class_idx = fb.add_class("HasCyclicStruct", 0, &[]);
        fb.add_property("P", "StructProperty", class_idx, 1, "Uncategorized", Some(actual_a_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let err = resolve_class("Pkg.HasCyclicStruct", &mut ctx).unwrap_err();
        assert!(matches!(err, ResolveError::MalformedSchema { .. }), "expected MalformedSchema, got {err:?}");
    }

    // Post-review fix: a DIFFERENT cycle from the `sup`-chain one above -- two structs that
    // reference EACH OTHER through an ordinary `StructProperty` MEMBER (A has a member of type B,
    // B has a member of type A), not through `sup`. Both structs are individually well-formed;
    // only the Step 5.5 `types`-closure WALK (`collect_struct_type`/`member_type_shape`) is
    // recursive here, and it needs its OWN `in_progress` guard (mirroring `struct_members_
    // with_super_rec`'s `seen`-set) since neither the `sup`-chain guard nor the Children/Next
    // 256-iteration cap covers this path at all. Same two-hop forward-prediction construction as
    // the `sup`-cycle test above, applied to a member `type_ref` instead of `sup`.
    #[test]
    fn struct_member_cycle_errors_instead_of_stack_overflowing() {
        let mut fb = fixture::FixtureBuilder::new();
        const A_MEMBERS: usize = 1;
        const B_MEMBERS: usize = 1;
        let a_start = fb.next_export_index();
        let predicted_b_idx = a_start + A_MEMBERS as i64 + 1 + B_MEMBERS as i64;
        let actual_a_idx = fb.add_struct_with_members("A", 0, 0, &[
            ("M", "StructProperty", 1, "Uncategorized", Some(predicted_b_idx)),
        ]);
        assert_eq!(actual_a_idx, a_start + A_MEMBERS as i64);
        let actual_b_idx = fb.add_struct_with_members("B", 0, 0, &[ // B's member type_ref is A's
            ("N", "StructProperty", 1, "Uncategorized", Some(actual_a_idx)), // REAL, already-known index.
        ]);
        assert_eq!(actual_b_idx, predicted_b_idx); // the whole trick only works if BOTH asserts hold

        let class_idx = fb.add_class("HasCyclicMemberStruct", 0, &[]);
        fb.add_property("P", "StructProperty", class_idx, 1, "Uncategorized", Some(actual_a_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let err = resolve_class("Pkg.HasCyclicMemberStruct", &mut ctx).unwrap_err();
        assert!(matches!(err, ResolveError::MalformedSchema { .. }), "expected MalformedSchema, got {err:?}");
    }

    // --- Step 5.65: a non-property sibling in the Children/Next chain is skipped but followed ---

    // Reproduces `Core.Scale`'s own real shape: a struct whose `Children` chain starts at an
    // `Enum` export (`ESheerAxis`), followed by three real members -- the enum must be ABSENT
    // from the member list (but its own `Next` still followed), and contribute NO bytes to the
    // struct's own binary default value.
    #[test]
    fn struct_children_chain_skips_non_property_sibling_but_follows_its_next() {
        let mut fb = fixture::FixtureBuilder::new();
        // `add_struct_with_members_ex` pushes members via `.rev()`, last-declared first, so the
        // first-declared member lands at `sibling_idx + members.len()`, NOT `sibling_idx + 1`
        // (round 16's review finding) -- predict accordingly.
        let sibling_idx = fb.next_export_index();
        let members: &[(&str, &str, u32, &str, Option<i64>)] = &[
            ("Scale", "FloatProperty", 1, "Uncategorized", None),
            ("SheerRate", "FloatProperty", 1, "Uncategorized", None),
            ("SheerAxis", "ByteProperty", 1, "Uncategorized", None),
        ];
        let esheeraxis_idx = fb.add_enum_ex("ESheerAxis", 0, &["SHEER_None", "SHEER_ZX"],
            sibling_idx + members.len() as i64);
        assert_eq!(esheeraxis_idx, sibling_idx, "the enum sibling must land at the predicted index");
        let scale_idx = fb.add_struct_with_members_ex("Scale", 0, 0, members, Some(esheeraxis_idx));

        let value_bin = fixture::encode_struct_value_bin(&[
            fixture::StructMemberValue::Float(2.0),
            fixture::StructMemberValue::Float(0.5),
            fixture::StructMemberValue::Byte(1),
        ]);
        let scale_name_idx = fb.name("Scale");
        let prop_name_idx = fb.name("S");
        let mut tags = fixture::encode_struct_tag(prop_name_idx, scale_name_idx, None, &value_bin);
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasScale", 0, &tags);
        fb.add_property("S", "StructProperty", class_idx, 1, "Uncategorized", Some(scale_idx));

        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasScale", &mut ctx).unwrap();

        let TypeShape::Struct { members: type_members } = &res.types["Pkg.Scale"]
            else { panic!("expected a struct shape") };
        let names: Vec<&str> = type_members.iter().map(|m| m.name.as_str()).collect();
        assert_eq!(names, vec!["Scale", "SheerRate", "SheerAxis"],
            "the enum sibling is absent from the member list");

        let prop = res.class.props.iter().find(|p| prop_name(p) == "S").unwrap();
        let DefaultValue::Struct(map) = prop_struct_default(prop) else { panic!("expected a struct default") };
        assert_eq!(map.get("Scale"), Some(&DefaultValue::Scalar("2".into())));
        assert_eq!(map.get("SheerRate"), Some(&DefaultValue::Scalar("0.5".into())));
        assert_eq!(map.get("SheerAxis"), Some(&DefaultValue::Scalar("1".into())),
            "the enum sibling contributes NO bytes -- only the 3 real members do");
    }

    // --- Step 5.7: cross-package (imported) type_ref resolution ---

    // Test 1: an imported struct -- "Child" class property's `type_ref` imports "Parent"'s own
    // "Vector" struct. Resolves to ("Parent", Vector's real index), and the identity key is under
    // the OWNER's package name ("Parent"), not the referencing package's ("Child").
    #[test]
    fn resolve_type_export_resolves_an_imported_struct_across_packages() {
        let mut fb_parent = fixture::FixtureBuilder::new();
        fb_parent.add_struct_with_members("Vector", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
            ("Y", "FloatProperty", 1, "Uncategorized", None),
            ("Z", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let parent_buf = fb_parent.build();

        let mut fb_child = fixture::FixtureBuilder::new();
        let vector_type_ref = fb_child.import_type_in_package("Vector", "Parent");
        let class_idx = fb_child.add_class("UsesVector", 0, &[]);
        fb_child.add_property("Loc", "StructProperty", class_idx, 1, "Uncategorized", Some(vector_type_ref));
        let child_buf = fb_child.build();

        let mut ctx = ResolutionContext::new();
        ctx.add_package("Parent", parent_buf).unwrap();
        ctx.add_package("Child", child_buf).unwrap();
        let res = resolve_class("Child.UsesVector", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Loc").unwrap();
        match prop {
            ResolvedProp::Struct { struct_type, .. } =>
                assert_eq!(struct_type.as_str(), "Parent.Vector",
                    "keyed under the OWNER's package name, not the referencing package's"),
            other => panic!("expected a struct prop, got {other:?}"),
        }
        assert!(res.types.contains_key("Parent.Vector"));
    }

    // Test 2: an imported enum -- assert the resolved enum VALUES (via the enum-body decode) match
    // what "Parent" declared, and the zero-fallback default is the enum's own first value name.
    #[test]
    fn resolve_type_export_resolves_an_imported_enum_and_decodes_its_values() {
        let mut fb_parent = fixture::FixtureBuilder::new();
        fb_parent.add_enum("EWeather", 0, &["Sunny", "Rainy", "Foggy"]);
        let parent_buf = fb_parent.build();

        let mut fb_child = fixture::FixtureBuilder::new();
        let weather_type_ref = fb_child.import_type_in_package("EWeather", "Parent");
        let class_idx = fb_child.add_class("UsesWeather", 0, &[]);
        fb_child.add_property("Mode", "ByteProperty", class_idx, 1, "Uncategorized", Some(weather_type_ref));
        let child_buf = fb_child.build();

        let mut ctx = ResolutionContext::new();
        ctx.add_package("Parent", parent_buf).unwrap();
        ctx.add_package("Child", child_buf).unwrap();
        let res = resolve_class("Child.UsesWeather", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Mode").unwrap();
        match prop {
            ResolvedProp::Enum { enum_type, default_value, .. } => {
                assert_eq!(enum_type.as_str(), "Parent.EWeather");
                assert_eq!(default_value.as_str(), "Sunny", "zero fallback: the enum's own first value name");
            }
            other => panic!("expected an enum prop, got {other:?}"),
        }
        let TypeShape::Enum { values } = &res.types["Parent.EWeather"] else { panic!("expected an enum shape") };
        assert_eq!(values, &vec!["Sunny".to_string(), "Rainy".to_string(), "Foggy".to_string()]);
    }

    // Test 3: the SAME imported-struct fixture as Test 1, but "Parent" is NEVER added to the
    // context -- `resolve_class` on "Child"'s class returns `MissingPackage("Parent")`.
    #[test]
    fn resolve_type_export_on_a_never_added_owning_package_returns_missing_package() {
        let mut fb_child = fixture::FixtureBuilder::new();
        let vector_type_ref = fb_child.import_type_in_package("Vector", "Parent");
        let class_idx = fb_child.add_class("UsesVector", 0, &[]);
        fb_child.add_property("Loc", "StructProperty", class_idx, 1, "Uncategorized", Some(vector_type_ref));
        let child_buf = fb_child.build();

        let mut ctx = ResolutionContext::new();
        ctx.add_package("Child", child_buf).unwrap(); // "Parent" deliberately never added
        let err = resolve_class("Child.UsesVector", &mut ctx).unwrap_err();
        assert!(matches!(err, ResolveError::MissingPackage(ref name) if name == "Parent"),
            "expected MissingPackage(\"Parent\"), got {err:?}");
    }

    // Test 4: declaring-package relativity -- a THREE-package chain, "Child" (class `C` extends
    // `Parent.P`) -> "Parent" (class `P` declares a `type_ref`-carrying property whose target
    // lives in "GrandParent") -> "GrandParent" (the actual struct). Resolving `C`'s INHERITED
    // property (declared in `P`, not `C`) must resolve its `type_ref` against `Parent`'s OWN
    // tables (where it was declared), not `Child`'s -- the exact silent-wrong-data bug this
    // mechanism exists to prevent (swapping which package's tables get used would resolve to the
    // wrong type or fail with `MissingPackage` naming the WRONG package).
    #[test]
    fn inherited_prop_type_ref_resolves_against_its_declaring_package_not_the_leaf() {
        let mut fb_gp = fixture::FixtureBuilder::new();
        fb_gp.add_struct_with_members("Vector", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let gp_buf = fb_gp.build();

        let mut fb_parent = fixture::FixtureBuilder::new();
        let vector_type_ref = fb_parent.import_type_in_package("Vector", "GrandParent");
        let p_idx = fb_parent.add_class("P", 0, &[]);
        fb_parent.add_property("Loc", "StructProperty", p_idx, 1, "Uncategorized", Some(vector_type_ref));
        let parent_buf = fb_parent.build();

        let mut fb_child = fixture::FixtureBuilder::new();
        let p_super_ref = fb_child.import_type_in_package("P", "Parent");
        fb_child.add_class("C", p_super_ref, &[]);
        let child_buf = fb_child.build();

        let mut ctx = ResolutionContext::new();
        ctx.add_package("GrandParent", gp_buf).unwrap();
        ctx.add_package("Parent", parent_buf).unwrap();
        ctx.add_package("Child", child_buf).unwrap();
        let res = resolve_class("Child.C", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Loc").unwrap();
        match prop {
            ResolvedProp::Struct { struct_type, .. } =>
                assert_eq!(struct_type.as_str(), "GrandParent.Vector"),
            other => panic!("expected a struct prop, got {other:?}"),
        }
        assert!(res.types.contains_key("GrandParent.Vector"));
    }

    // --- Step 6: name-based exclusion chain (HARD_REJECT/TYPED_FIELDS/is_computed_key), plus the
    // top-level KIND-based `_is_excluded_kind` case (the RECURSIVE struct-member case -- an
    // excluded member decoded-but-omitted inside an included struct -- is already covered by
    // `resolve_class_struct_default_tree_omits_excluded_member_but_still_consumes_its_bytes` above,
    // built for Step 4.6's own struct default-tree assembly) ---

    #[test]
    fn resolve_class_excludes_a_hard_reject_named_prop() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("HasHardReject", 0, &[]);
        fb.add_property("KeyNum", "IntProperty", class_idx, 1, "Uncategorized", None);
        fb.add_property("Other", "IntProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasHardReject", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert!(!names.contains(&"KeyNum"), "a HARD_REJECT name must be excluded from the resolved shape");
        assert!(names.contains(&"Other"), "an ordinary prop alongside it still resolves");
    }

    #[test]
    fn resolve_class_excludes_a_typed_field_named_prop() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("HasTypedFieldName", 0, &[]);
        fb.add_property("MainScale", "IntProperty", class_idx, 1, "Uncategorized", None);
        fb.add_property("Other", "IntProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasTypedFieldName", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert!(!names.contains(&"MainScale"),
            "a TYPED_FIELDS name must be excluded -- it gets its own typed-field emission (Step 8, later work), never a plain prop");
        assert!(names.contains(&"Other"));
    }

    #[test]
    fn resolve_class_excludes_a_computed_key_named_prop() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("HasComputedKey", 0, &[]);
        fb.add_property("BSelected", "BoolProperty", class_idx, 1, "Uncategorized", None); // _INGEST_NAMES
        fb.add_property("AIProfile0", "IntProperty", class_idx, 1, "Uncategorized", None); // _COMPUTED_PREFIXES
        fb.add_property("Other", "IntProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasComputedKey", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert!(!names.contains(&"BSelected"), "an _INGEST_NAMES-listed name must be excluded");
        assert!(!names.contains(&"AIProfile0"), "an AIProfile-prefixed name must be excluded");
        assert!(names.contains(&"Other"));
    }

    #[test]
    fn resolve_class_excludes_an_excluded_kind_prop_at_top_level() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("HasObjectRef", 0, &[]);
        fb.add_property("Owner", "ObjectProperty", class_idx, 1, "Uncategorized", None);
        fb.add_property("Other", "IntProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasObjectRef", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert!(!names.contains(&"Owner"), "an ObjectProperty has no wire shape and must be excluded");
        assert!(names.contains(&"Other"));
    }

    // --- Step 6.5: a single unresolvable struct-member/array-element LEAF fails the WHOLE
    // resolve_class call -- no partial ClassResolution, no silent omission, no note field. A
    // DIFFERENT failure surface from a class/Super-chain itself not being found. ---

    #[test]
    fn resolve_class_unresolvable_member_type_fails_whole_call_named_by_member() {
        let mut fb_parent = fixture::FixtureBuilder::new();
        fb_parent.add_class("Placeholder", 0, &[]); // "Parent" is added but declares no "Vector" struct
        let parent_buf = fb_parent.build();

        let mut fb_child = fixture::FixtureBuilder::new();
        let vector_type_ref = fb_child.import_type_in_package("Vector", "Parent");
        let class_idx = fb_child.add_class("HasBadMember", 0, &[]);
        fb_child.add_property("Loc", "StructProperty", class_idx, 1, "Uncategorized", Some(vector_type_ref));
        let child_buf = fb_child.build();

        let mut ctx = ResolutionContext::new();
        ctx.add_package("Parent", parent_buf).unwrap();
        ctx.add_package("Child", child_buf).unwrap();
        let err = resolve_class("Child.HasBadMember", &mut ctx).unwrap_err();
        match err {
            ResolveError::MalformedSchema { class, reason } => {
                assert_eq!(class, "Child.HasBadMember", "named by the class ORIGINALLY passed to resolve_class");
                assert!(reason.contains("member Loc"), "reason must name the offending member: {reason}");
                assert!(reason.contains("Vector"), "reason must say why it's unresolvable: {reason}");
            }
            other => panic!("expected MalformedSchema, got {other:?}"),
        }
    }

    #[test]
    fn resolve_class_distinguishes_class_not_found_from_one_unresolvable_member() {
        // The complement of the test above: a class that can't be found AT ALL is
        // `UnresolvableClass`, never `MalformedSchema` -- a genuinely different failure surface
        // from "the class resolves fine except for one member's own type".
        let mut fb = fixture::FixtureBuilder::new();
        fb.add_class("RealClass", 0, &[]);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let err = resolve_class("Pkg.NoSuchClass", &mut ctx).unwrap_err();
        assert!(matches!(err, ResolveError::UnresolvableClass(ref name) if name == "Pkg.NoSuchClass"),
            "expected UnresolvableClass, got {err:?}");
    }

    // --- Step 6.6: two real corpus exceptions in a property export's own header decode ---

    // (a) A property export's own leading tagged-prop header is not always a bare "None" --
    // `Engine.Actor.Touching` carries a real IntProperty tag first. Reading one bare compact as the
    // terminator would desync every fixed field that follows (ArrayDim/PropertyFlags/Category/
    // type_ref); this proves the production decoder reads it via the full `read_property_tags`.
    #[test]
    fn decode_property_export_reads_a_leading_real_tag_not_just_bare_none() {
        let mut fb = fixture::FixtureBuilder::new();
        let struct_idx = fb.add_struct_with_members("Touch", 0, 0, &[
            ("Dummy", "IntProperty", 1, "Uncategorized", None),
        ]);
        let leading_name = fb.name("SomeLeadingTag"); // a REAL non-"None" name -- index 0 IS "None"
                                                        // and would terminate read_property_tags
                                                        // immediately, proving nothing.
        let mut header = fixture::encode_fixed_tag(leading_name, 2, None, &0i32.to_le_bytes()); // an IntProperty tag
        header.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasTouchingShapedProp", 0, &[]);
        fb.add_property_ex("Touching", "StructProperty", class_idx, &header, 1, 0, "Movement", 0, Some(struct_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasTouchingShapedProp", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Touching")
            .expect("must decode past the real leading tag, not desync into exclusion or an error");
        assert_eq!(prop_category(prop), "Movement", "Category must survive the extra leading tag");
        match prop {
            ResolvedProp::Struct { struct_type, .. } => assert_eq!(struct_type, "Pkg.Touch"),
            other => panic!("expected a struct prop, got {other:?}"),
        }
    }

    // (b) `CPF_NET` (0x20) means a 2-byte RepOffset follows Category, BEFORE type_ref -- a decoder
    // that forgets the skip reads RepOffset's own low byte as type_ref's first byte. `0x8040` sets
    // the compact-index continuation bit in that low byte, so a missed skip chains into the wrong
    // final type_ref (an all-zero RepOffset would make this test vacuous -- see `property_body`'s
    // own doc).
    #[test]
    fn decode_property_export_skips_cpf_net_rep_offset_before_type_ref() {
        let mut fb = fixture::FixtureBuilder::new();
        let struct_idx = fb.add_struct_with_members("Vec3", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let class_idx = fb.add_class("HasNetProp", 0, &[]);
        fb.add_property_ex("Loc", "StructProperty", class_idx, &fixture::none_terminator(0),
            1, CPF_NET, "Movement", 0x8040, Some(struct_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasNetProp", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Loc")
            .expect("must decode despite CPF_NET's own RepOffset field");
        match prop {
            ResolvedProp::Struct { struct_type, .. } => assert_eq!(struct_type, "Pkg.Vec3",
                "a decoder that fails to skip the 2 RepOffset bytes reads 0x40 as type_ref's own first byte"),
            other => panic!("expected a struct prop, got {other:?}"),
        }
    }

    // --- Task 4 Step 7: canonicalization -- enum ordinal->name, format_float, and confirming
    // _dequote/_maybe_comma_sugar (both WRITE-path-only in the real Python, `propedit/edit.py:80`'s
    // `effective_value` stored branch and `propedit/structtext.py:116-132`) are NOT reproduced by
    // this function, which only ever renders an already-decoded class default. ---

    #[test]
    fn format_float_renders_integral_values_bare() {
        assert_eq!(format_float(24.0), "24");
        assert_eq!(format_float(-10.0), "-10");
    }

    #[test]
    fn format_float_trims_fractional_values_to_minimal_decimals() {
        assert_eq!(format_float(0.5), "0.5");
        assert_eq!(format_float(-10.25), "-10.25");
    }

    #[test]
    fn format_float_negative_zero_renders_bare_zero_not_minus_zero() {
        // Rust's `Display` preserves the float sign bit through `.trunc()`; Python's `int(-0.0)`
        // does not. Casting to `i64` before `.to_string()` (not `v.trunc().to_string()` on the raw
        // float) is what avoids emitting "-0" here.
        assert_eq!(format_float(-0.0_f64), "0");
    }

    #[test]
    fn format_float_tiny_magnitude_rounds_to_zero_not_scientific_notation() {
        // spec §6's own cited divergence case: a value too small to survive 6 decimal places must
        // still render "0", never Rust's default scientific `Display` form ("0.0000001").
        assert_eq!(format_float(1e-7), "0");
    }

    #[test]
    fn resolve_class_stated_enum_default_renders_canonical_name_not_raw_ordinal() {
        let mut fb = fixture::FixtureBuilder::new();
        let enum_idx = fb.add_enum("EMode", 0, &["FIRST", "SECOND", "THIRD"]);
        let mode_name = fb.name("Mode");
        let mut tags = fixture::encode_fixed_tag(mode_name, 1, None, &[1u8]); // ptype 1 = byte, ordinal 1
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasStatedEnum", 0, &tags);
        fb.add_property("Mode", "ByteProperty", class_idx, 1, "Uncategorized", Some(enum_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasStatedEnum", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Mode").unwrap();
        assert_eq!(prop_default_text(prop), "SECOND",
            "a STATED byte default with an enum type_ref canonicalizes to its name, not the raw ordinal \"1\"");
    }

    // An FString's own wire form: compact byte length INCLUDING the terminating NUL, then that
    // many latin-1 bytes (`package_read::read_fstring`'s exact inverse).
    fn fstring_value_bytes(s: &str) -> Vec<u8> {
        let mut bytes = s.as_bytes().to_vec();
        bytes.push(0);
        let mut out = fixture::encode_compact_index(bytes.len() as i64);
        out.extend_from_slice(&bytes);
        out
    }

    #[test]
    fn resolve_class_str_default_is_never_dequoted() {
        let mut fb = fixture::FixtureBuilder::new();
        let name_idx = fb.name("Msg");
        let mut tags = fixture::encode_fixed_tag(name_idx, 13, None, &fstring_value_bytes("\"hello\""));
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasQuotedDefault", 0, &tags);
        fb.add_property("Msg", "StrProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasQuotedDefault", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Msg").unwrap();
        // `_dequote` (`propedit/base.py:50-58`) strips one wrapping quote pair from an ACTOR'S OWN
        // STORED text (`effective_value`'s stored branch, `propedit/edit.py:80`) -- this function
        // never sees actor state at all, only a decoded class default; a literal wrapping quote
        // pair in the FString bytes is real string content here, never T3D quoting syntax to strip.
        assert_eq!(prop_default_text(prop), "\"hello\"", "a class default is never dequoted");
    }

    #[test]
    fn resolve_class_str_default_does_not_apply_vector_comma_sugar() {
        let mut fb = fixture::FixtureBuilder::new();
        let name_idx = fb.name("Coords");
        let mut tags = fixture::encode_fixed_tag(name_idx, 13, None, &fstring_value_bytes("1,2,3"));
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasCommaDefault", 0, &tags);
        fb.add_property("Coords", "StrProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasCommaDefault", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Coords").unwrap();
        // `_maybe_comma_sugar` (`propedit/structtext.py:116-132`) is a WRITE-path convenience that
        // reinterprets a bare `"1,2,3"` a user TYPES as `(X=1,Y=2,Z=3)` for a Vector/Rotator struct
        // prop. This function never joins a decoded value into text and reparses it -- a comma
        // anywhere in a scalar default passes through byte-for-byte.
        assert_eq!(prop_default_text(prop), "1,2,3");
    }

    // --- Task 4 Step 8: TYPED_FIELDS (Location/MainScale/PostScale) shape+defaults emission ---

    #[test]
    fn resolve_class_emits_typed_fields_with_real_shape_and_defaults() {
        let mut fb = fixture::FixtureBuilder::new();

        // A real, resolvable Vector-equivalent struct for `Location`'s own type.
        let vector_idx = fb.add_struct_with_members("Vector", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
            ("Y", "FloatProperty", 1, "Uncategorized", None),
            ("Z", "FloatProperty", 1, "Uncategorized", None),
        ]);

        // `Core.Scale`'s own real shape (Step 5.65): `ESheerAxis` (Enum) spliced FIRST into
        // `Scale`'s own Children chain, followed by its 3 real members.
        const SCALE_MEMBERS: usize = 3; // Scale(struct), SheerRate(float), SheerAxis(byte)
        let enum_idx = fb.next_export_index();
        let first_member_idx = enum_idx + SCALE_MEMBERS as i64;
        let scale_idx = first_member_idx + 1;
        let actual_enum_idx = fb.add_enum_ex("ESheerAxis", scale_idx as i32,
            &["SHEER_None", "SHEER_XY", "SHEER_XZ", "SHEER_YX", "SHEER_YZ", "SHEER_ZX", "SHEER_ZY"],
            first_member_idx);
        assert_eq!(actual_enum_idx, enum_idx);
        let actual_scale_idx = fb.add_struct_with_members_ex("Scale", 0, 0, &[
            ("Scale", "StructProperty", 1, "Uncategorized", Some(vector_idx)),
            ("SheerRate", "FloatProperty", 1, "Uncategorized", None),
            ("SheerAxis", "ByteProperty", 1, "Uncategorized", Some(enum_idx)),
        ], Some(enum_idx));
        assert_eq!(actual_scale_idx, scale_idx);

        // Location: a STATED class default (X=100,Y=200,Z=300).
        let loc_value = fixture::encode_struct_value_bin(&[
            fixture::StructMemberValue::Float(100.0),
            fixture::StructMemberValue::Float(200.0),
            fixture::StructMemberValue::Float(300.0),
        ]);
        let location_name_idx = fb.name("Location");
        let vector_name_idx = fb.name("Vector");
        let mut tags = fixture::encode_struct_tag(location_name_idx, vector_name_idx, None, &loc_value);

        // MainScale: a STATED class default, SheerAxis=0 (ordinal) -- must canonicalize to
        // "SHEER_None", matching `Engine.Brush`'s own real worked example
        // (`gui-inspector-props-payload-redesign/spec.md`'s `MainScale` example).
        let mainscale_value = fixture::encode_struct_value_bin(&[
            fixture::StructMemberValue::Struct(&[
                fixture::StructMemberValue::Float(1.0),
                fixture::StructMemberValue::Float(1.0),
                fixture::StructMemberValue::Float(1.0),
            ]),
            fixture::StructMemberValue::Float(0.0),
            fixture::StructMemberValue::Byte(0),
        ]);
        let mainscale_name_idx = fb.name("MainScale");
        let scale_name_idx = fb.name("Scale");
        tags.extend_from_slice(&fixture::encode_struct_tag(mainscale_name_idx, scale_name_idx, None, &mainscale_value));
        tags.extend_from_slice(&fixture::none_terminator(0));

        let class_idx = fb.add_class("HasTypedFields", 0, &tags);
        fb.add_property("Location", "StructProperty", class_idx, 1, "Movement", Some(vector_idx));
        fb.add_property("MainScale", "StructProperty", class_idx, 1, "Brush", Some(actual_scale_idx));
        fb.add_property("PostScale", "StructProperty", class_idx, 1, "Brush", Some(actual_scale_idx));
        // PostScale states NO class default at all -- must fall back to typed_field_fallback's own
        // separate constants, never the generic zero rule.

        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasTypedFields", &mut ctx).unwrap();

        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert_eq!(names, vec!["Location", "MainScale", "PostScale"],
            "the three TYPED_FIELDS leaves come first, in this fixed order (Step 9)");
        assert!(res.types.contains_key("Pkg.Scale.ESheerAxis"),
            "SheerAxis's own canonicalization is grounded on a real resolved enum, in the types closure");

        let location = res.class.props.iter().find(|p| prop_name(p) == "Location").unwrap();
        assert_eq!(prop_category(location), "Movement");
        match location {
            ResolvedProp::Struct { struct_type, .. } => assert_eq!(struct_type.as_str(), "Pkg.Vector"),
            other => panic!("expected a struct prop, got {other:?}"),
        }
        assert_eq!(prop_struct_default(location), &DefaultValue::Struct(BTreeMap::from([
            ("X".to_string(), DefaultValue::Scalar("100".to_string())),
            ("Y".to_string(), DefaultValue::Scalar("200".to_string())),
            ("Z".to_string(), DefaultValue::Scalar("300".to_string())),
        ])));

        let mainscale = res.class.props.iter().find(|p| prop_name(p) == "MainScale").unwrap();
        assert_eq!(prop_category(mainscale), "Brush");
        match mainscale {
            ResolvedProp::Struct { struct_type, .. } => assert_eq!(struct_type.as_str(), "Pkg.Scale"),
            other => panic!("expected a struct prop, got {other:?}"),
        }
        assert_eq!(prop_struct_default(mainscale), &DefaultValue::Struct(BTreeMap::from([
            ("Scale".to_string(), DefaultValue::Struct(BTreeMap::from([
                ("X".to_string(), DefaultValue::Scalar("1".to_string())),
                ("Y".to_string(), DefaultValue::Scalar("1".to_string())),
                ("Z".to_string(), DefaultValue::Scalar("1".to_string())),
            ]))),
            ("SheerRate".to_string(), DefaultValue::Scalar("0".to_string())),
            ("SheerAxis".to_string(), DefaultValue::Scalar("SHEER_None".to_string())),
        ])), "a STATED SheerAxis=0 default canonicalizes to its enum name, matching Engine.Brush's real MainScale");

        let postscale = res.class.props.iter().find(|p| prop_name(p) == "PostScale").unwrap();
        assert_eq!(prop_category(postscale), "Brush");
        match postscale {
            ResolvedProp::Struct { struct_type, .. } => assert_eq!(struct_type.as_str(), "Pkg.Scale"),
            other => panic!("expected a struct prop, got {other:?}"),
        }
        assert_eq!(prop_struct_default(postscale), &DefaultValue::Struct(BTreeMap::from([
            ("Scale".to_string(), DefaultValue::Struct(BTreeMap::from([
                ("X".to_string(), DefaultValue::Scalar("1".to_string())),
                ("Y".to_string(), DefaultValue::Scalar("1".to_string())),
                ("Z".to_string(), DefaultValue::Scalar("1".to_string())),
            ]))),
            ("SheerRate".to_string(), DefaultValue::Scalar("0".to_string())),
            ("SheerAxis".to_string(), DefaultValue::Scalar("SHEER_ZX".to_string())),
        ])), "no class default anywhere for PostScale -- the SEPARATE typed_field_fallback constants, not the generic zero rule");
    }

    #[test]
    fn resolve_class_typed_fields_absent_when_the_class_never_declares_them() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("NoTypedFields", 0, &[]);
        fb.add_property("Other", "IntProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.NoTypedFields", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert_eq!(names, vec!["Other"],
            "a class that declares none of Location/MainScale/PostScale emits none of them -- no forced entry, no error");
    }

    // --- Task 4 Step 9: props-order normativity ---

    #[test]
    fn resolve_class_props_order_is_typed_fields_first_then_generic_walk_order() {
        let mut fb = fixture::FixtureBuilder::new();
        let vector_idx = fb.add_struct_with_members("Vector", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
            ("Y", "FloatProperty", 1, "Uncategorized", None),
            ("Z", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let class_idx = fb.add_class("OrderTest", 0, &[]);
        // Declared in an order that would NOT match the expected output if `props` simply followed
        // fixture declaration order.
        fb.add_property("Zeta", "IntProperty", class_idx, 1, "Uncategorized", None);
        fb.add_property("Location", "StructProperty", class_idx, 1, "Movement", Some(vector_idx));
        fb.add_property("Alpha", "IntProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.OrderTest", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert_eq!(names, vec!["Location", "Zeta", "Alpha"],
            "Location is unconditionally first, then the generic walk's own declaration order -- \
             never alphabetical, never the fixture's own declaration order alone");
    }

    // --- Task 4 Step 10: category never null, and the real non-zero "None"-spelled inverse ---

    #[test]
    fn resolve_class_category_index_zero_renders_uncategorized() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("HasNoneCategory", 0, &[]);
        fb.add_property("Foo", "IntProperty", class_idx, 1, "None", None); // interns to index 0
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasNoneCategory", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Foo").unwrap();
        assert_eq!(prop_category(prop), "Uncategorized");
    }

    #[test]
    fn resolve_class_category_text_that_itself_spells_none_at_a_nonzero_index_is_never_normalized() {
        let mut fb = fixture::FixtureBuilder::new();
        // A SECOND name-table entry that ALSO spells "None", at a genuinely DIFFERENT (non-zero)
        // index -- `name()`'s own dedup can't build this shape (a second `name("None")` call would
        // just reuse index 0), hence the dedup-bypassing push.
        let dup_none_idx = fb.push_name_allow_duplicate("None");
        assert_ne!(dup_none_idx, 0, "must be a genuinely different name-table slot than index 0's own None");
        let class_idx = fb.add_class("HasDupNoneCategory", 0, &[]);
        fb.add_property_with_category_idx("Foo", "IntProperty", class_idx, 1, dup_none_idx, None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasDupNoneCategory", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Foo").unwrap();
        assert_eq!(prop_category(prop), "None",
            "a NON-ZERO name-table index that spells \"None\" renders literally, never normalized to Uncategorized");
    }

    // --- Task 4 Step 11: positional, never-collapsed static array defaults ---

    #[test]
    fn resolve_class_static_array_renders_all_stated_defaults_positionally() {
        let mut fb = fixture::FixtureBuilder::new();
        let name_idx = fb.name("Ranks");
        let mut tags = fixture::encode_fixed_tag(name_idx, 2, Some(0), &10i32.to_le_bytes());
        tags.extend_from_slice(&fixture::encode_fixed_tag(name_idx, 2, Some(1), &10i32.to_le_bytes()));
        tags.extend_from_slice(&fixture::encode_fixed_tag(name_idx, 2, Some(2), &20i32.to_le_bytes()));
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasStatedArray", 0, &tags);
        fb.add_property("Ranks", "IntProperty", class_idx, 3, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasStatedArray", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Ranks").unwrap();
        match prop {
            ResolvedProp::Array { array_dim, default_value, element, .. } => {
                assert_eq!(*array_dim, 3);
                assert!(matches!(element, ArrayElementKind::Scalar(ScalarKind::Int)));
                assert_eq!(default_value, &vec![
                    DefaultValue::Scalar("10".to_string()),
                    DefaultValue::Scalar("10".to_string()),
                    DefaultValue::Scalar("20".to_string()),
                ], "two identical values at different indices must BOTH render, never collapsed");
            }
            other => panic!("expected an array prop, got {other:?}"),
        }
    }

    #[test]
    fn resolve_class_sparse_static_array_default_fills_unstated_indices_with_zero() {
        let mut fb = fixture::FixtureBuilder::new();
        let name_idx = fb.name("Flags");
        // Only indices 0 and 2 stated; 1 and 3 must fall back to the generic zero rule.
        let mut tags = fixture::encode_fixed_tag(name_idx, 2, Some(0), &5i32.to_le_bytes());
        tags.extend_from_slice(&fixture::encode_fixed_tag(name_idx, 2, Some(2), &7i32.to_le_bytes()));
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasSparseArray", 0, &tags);
        fb.add_property("Flags", "IntProperty", class_idx, 4, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasSparseArray", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Flags").unwrap();
        match prop {
            ResolvedProp::Array { array_dim, default_value, .. } => {
                assert_eq!(*array_dim, 4);
                assert_eq!(default_value, &vec![
                    DefaultValue::Scalar("5".to_string()),
                    DefaultValue::Scalar("0".to_string()),
                    DefaultValue::Scalar("7".to_string()),
                    DefaultValue::Scalar("0".to_string()),
                ], "the Vec<DefaultValue> is always array_dim long, positionally, with no gaps");
            }
            other => panic!("expected an array prop, got {other:?}"),
        }
    }

    #[test]
    fn resolve_class_static_array_of_structs_each_element_is_a_tree_not_a_flat_string() {
        let mut fb = fixture::FixtureBuilder::new();
        let vector_idx = fb.add_struct_with_members("Vector", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
            ("Y", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let name_idx = fb.name("Points");
        let vector_name_idx = fb.name("Vector");
        let elem0 = fixture::encode_struct_value_bin(&[
            fixture::StructMemberValue::Float(1.0), fixture::StructMemberValue::Float(2.0),
        ]);
        let mut tags = fixture::encode_struct_tag(name_idx, vector_name_idx, Some(0), &elem0);
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasStructArray", 0, &tags);
        fb.add_property("Points", "StructProperty", class_idx, 2, "Uncategorized", Some(vector_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let res = resolve_class("Pkg.HasStructArray", &mut ctx).unwrap();
        let prop = res.class.props.iter().find(|p| prop_name(p) == "Points").unwrap();
        match prop {
            ResolvedProp::Array { array_dim, default_value, element, .. } => {
                assert_eq!(*array_dim, 2);
                assert!(matches!(element, ArrayElementKind::Struct(k) if k.as_str() == "Pkg.Vector"));
                assert_eq!(default_value[0], DefaultValue::Struct(BTreeMap::from([
                    ("X".to_string(), DefaultValue::Scalar("1".to_string())),
                    ("Y".to_string(), DefaultValue::Scalar("2".to_string())),
                ])), "a struct element is its own recursive tree, never a flat joined string");
                assert_eq!(default_value[1], DefaultValue::Struct(BTreeMap::from([
                    ("X".to_string(), DefaultValue::Scalar("0".to_string())),
                    ("Y".to_string(), DefaultValue::Scalar("0".to_string())),
                ])), "the unstated second element falls back to the struct's own zero shape");
            }
            other => panic!("expected an array prop, got {other:?}"),
        }
    }

    // --- Task 4 Step 12: dotted-path convention (matches _canonical_path's literal array index) ---

    #[test]
    fn indexed_path_uses_a_literal_dotted_index_never_brackets() {
        assert_eq!(indexed_path("AlliancesEx", 2), "AlliancesEx.2");
    }

    #[test]
    fn resolve_class_array_element_shape_mismatch_is_named_with_the_dotted_index_convention() {
        let mut fb = fixture::FixtureBuilder::new();
        let vector_idx = fb.add_struct_with_members("Vector", 0, 0, &[
            ("X", "FloatProperty", 1, "Uncategorized", None),
            ("Y", "FloatProperty", 1, "Uncategorized", None),
        ]);
        let name_idx = fb.name("Points");
        // A SCALAR (int) default tag stated for array index 1, even though the schema below
        // declares "Points" as a StructProperty[2] array -- a real shape mismatch at ONE specific
        // index (`render_default_tag`'s own PT_INT branch is schema-agnostic, so this decodes fine
        // at the eager defaults-tag stage; the mismatch only surfaces once `render_prop` compares
        // the rendered shape against what "Points"'s own schema kind expects).
        let mut tags = fixture::encode_fixed_tag(name_idx, 2, Some(1), &7i32.to_le_bytes());
        tags.extend_from_slice(&fixture::none_terminator(0));
        let class_idx = fb.add_class("HasMismatchedArrayElement", 0, &tags);
        fb.add_property("Points", "StructProperty", class_idx, 2, "Uncategorized", Some(vector_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let err = resolve_class("Pkg.HasMismatchedArrayElement", &mut ctx).unwrap_err();
        match err {
            ResolveError::MalformedSchema { reason, .. } => {
                assert!(reason.contains("Points.1"),
                    "must name the specific mismatched element with a literal dotted index, not [1]/(1): {reason}");
            }
            other => panic!("expected MalformedSchema, got {other:?}"),
        }
    }

    // --- Task 4 Step 13: cross-package Super chain -- success, MissingPackage, UnresolvableClass ---

    #[test]
    fn resolve_class_cross_package_super_chain_succeeds_when_both_packages_are_added() {
        let mut fb_parent = fixture::FixtureBuilder::new();
        let parent_idx = fb_parent.add_class("Parent", 0, &[]);
        fb_parent.add_property("ParentProp", "IntProperty", parent_idx, 1, "Uncategorized", None);
        let parent_buf = fb_parent.build();

        let mut fb_child = fixture::FixtureBuilder::new();
        let parent_super_ref = fb_child.import_type_in_package("Parent", "Engine");
        let child_idx = fb_child.add_class("SomeClass", parent_super_ref, &[]);
        fb_child.add_property("ChildProp", "IntProperty", child_idx, 1, "Uncategorized", None);
        let child_buf = fb_child.build();

        let mut ctx = ResolutionContext::new();
        ctx.add_package("Child", child_buf).unwrap();
        ctx.add_package("Engine", parent_buf).unwrap();
        let res = resolve_class("Child.SomeClass", &mut ctx).unwrap();
        let names: Vec<&str> = res.class.props.iter().map(prop_name).collect();
        assert!(names.contains(&"ParentProp"), "the cross-package Super's own prop must be inherited");
        assert!(names.contains(&"ChildProp"));
    }

    #[test]
    fn resolve_class_cross_package_super_chain_missing_package_names_the_super_not_the_child() {
        let mut fb_child = fixture::FixtureBuilder::new();
        let parent_super_ref = fb_child.import_type_in_package("Parent", "Engine");
        fb_child.add_class("SomeClass", parent_super_ref, &[]);
        let child_buf = fb_child.build();

        let mut ctx = ResolutionContext::new();
        ctx.add_package("Child", child_buf).unwrap(); // "Engine" deliberately never added
        let err = resolve_class("Child.SomeClass", &mut ctx).unwrap_err();
        assert!(matches!(err, ResolveError::MissingPackage(ref name) if name == "Engine"),
            "expected MissingPackage(\"Engine\"), got {err:?}");
    }

    #[test]
    fn resolve_class_cross_package_unresolvable_class_name_is_unresolvable_class() {
        let mut fb_child = fixture::FixtureBuilder::new();
        fb_child.add_class("RealClass", 0, &[]);
        let child_buf = fb_child.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Child", child_buf).unwrap();
        let err = resolve_class("Child.NoSuchClass", &mut ctx).unwrap_err();
        assert!(matches!(err, ResolveError::UnresolvableClass(ref name) if name == "Child.NoSuchClass"),
            "expected UnresolvableClass, got {err:?}");
    }

    // --- Task 5: resolve_actor_props ---

    // Step 1: a whole-class resolve failure (missing package) degrades to `note`, never propagates
    // -- and the note's exact text uses Python's `!r`-style LITERAL SINGLE quotes around the actor
    // name, never Rust's `{:?}` debug format (which would emit double quotes instead).
    #[test]
    fn resolve_actor_props_degrades_missing_package_to_a_note_never_panics_or_errors() {
        let mut ctx = ResolutionContext::new(); // "Missing" package deliberately never added
        let result = resolve_actor_props("Bob", "Missing.Foo", &[], &mut ctx);
        assert!(result.sparse.is_empty());
        assert_eq!(result.note, Some(
            "actor 'Bob': schema unavailable (Missing.Foo) — cannot resolve effective props \
             (package not added: Missing)".to_string()));
    }

    // Step 2: an actor_props entry whose path doesn't exist in the resolved class's own shape is
    // silently skipped, never included in `sparse` (spec §2's orphan-path rule).
    #[test]
    fn resolve_actor_props_silently_skips_an_orphan_path() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("Simple", 0, &[]);
        fb.add_property("Health", "IntProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();
        let props = vec![
            ("Health".to_string(), "50".to_string()),
            ("Ghost".to_string(), "1".to_string()), // no such path in the class's own shape
        ];
        let result = resolve_actor_props("Bob", "Pkg.Simple", &props, &mut ctx);
        assert_eq!(result.note, None);
        let expected: BTreeMap<String, String> =
            [("Health".to_string(), "50".to_string())].into_iter().collect();
        assert_eq!(result.sparse, expected, "the orphan \"Ghost\" path must not appear at all");
    }

    // Step 3: an enum-typed leaf's STATED value canonicalizes the same way its default would --
    // a digit-text ordinal within range becomes its name; text already a name, or an out-of-range
    // ordinal, passes through unchanged (mirrors `propedit/edit.py`'s `_canonicalize_enum` exactly).
    #[test]
    fn resolve_actor_props_canonicalizes_a_stated_enum_ordinal_to_its_name() {
        let mut fb = fixture::FixtureBuilder::new();
        let enum_idx = fb.add_enum("EMode", 0, &["FIRST", "SECOND", "THIRD"]);
        let class_idx = fb.add_class("HasStatedEnum", 0, &[]);
        fb.add_property("Mode", "ByteProperty", class_idx, 1, "Uncategorized", Some(enum_idx));
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();

        let ordinal = vec![("Mode".to_string(), "1".to_string())];
        let result = resolve_actor_props("Bob", "Pkg.HasStatedEnum", &ordinal, &mut ctx);
        assert_eq!(result.sparse.get("Mode").map(String::as_str), Some("SECOND"),
            "a digit-text ordinal within range canonicalizes to its name");

        let already_a_name = vec![("Mode".to_string(), "THIRD".to_string())];
        let result = resolve_actor_props("Bob", "Pkg.HasStatedEnum", &already_a_name, &mut ctx);
        assert_eq!(result.sparse.get("Mode").map(String::as_str), Some("THIRD"),
            "text already a name passes through unchanged");

        let out_of_range = vec![("Mode".to_string(), "99".to_string())];
        let result = resolve_actor_props("Bob", "Pkg.HasStatedEnum", &out_of_range, &mut ctx);
        assert_eq!(result.sparse.get("Mode").map(String::as_str), Some("99"),
            "an out-of-range ordinal keeps the raw ordinal text, matching _canonicalize_enum exactly");
    }

    // Step 3 (the other real canonicalization, spec §3's port-items list): `_dequote` strips ONE
    // genuine wrapping quote pair off a non-enum leaf's stated text too -- an actor's own stored
    // text is real T3D quoting syntax to strip, unlike a class default (`resolve_class_str_default_
    // is_never_dequoted`, above).
    #[test]
    fn resolve_actor_props_dequotes_a_stated_scalar_value() {
        let mut fb = fixture::FixtureBuilder::new();
        let class_idx = fb.add_class("HasStr", 0, &[]);
        fb.add_property("Msg", "StrProperty", class_idx, 1, "Uncategorized", None);
        let buf = fb.build();
        let mut ctx = ResolutionContext::new();
        ctx.add_package("Pkg", buf).unwrap();

        let quoted = vec![("Msg".to_string(), "\"hello\"".to_string())];
        let result = resolve_actor_props("Bob", "Pkg.HasStr", &quoted, &mut ctx);
        assert_eq!(result.sparse.get("Msg").map(String::as_str), Some("hello"));

        // Embedded quotes belong to different words, not a wrapper -- ALL quotes are kept.
        let embedded = vec![("Msg".to_string(), "\"a\" and \"b\"".to_string())];
        let result = resolve_actor_props("Bob", "Pkg.HasStr", &embedded, &mut ctx);
        assert_eq!(result.sparse.get("Msg").map(String::as_str), Some("\"a\" and \"b\""));
    }
}
