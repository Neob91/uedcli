# Proposed exclusion: name-table ORDER for member-bearing classes (pure indexing)

## What reproduces exactly (byte-for-byte vs UCC)
Everything except one thing: every object BODY, all object/name/import table CONTENT, package
flags, GUID-aside header, `ClassFlags`, `ScriptTextCRC`, the defaults block, **import order**,
**export order**, and — for member-free classes — **name order**. `UscHello` compiles fully
byte-identical autonomously.

## The one residual
For a class with member vars, the **name-table ORDER** differs. Measured on `UscVars`: the name
SET, import order, and export order all match UCC; only the order of names in the name table
differs (member FNames like `Alpha`/`Beta`/`Gamma` interleave with stock names by an order UCC fixes
at compile time from its internal `FName`-registration sequence — property-type and defaults
dependent, not declaration order). Because bodies reference names by INDEX, a different name order
also shifts the name-index bytes inside bodies.

## Why it's a candidate exclusion (your criteria: inconsequential + very hard)
- **Functionally inconsequential — pure indexing.** Names are referenced only by table index; a
  package with the names permuted and all indices remapped is the *same* package to the engine — it
  loads and plays identically. This is the same class as the map-parity campaign's accepted
  export-table-order / `None`-hole exclusions (`NATIVE-MATERIALIZE.md`).
- **Very hard to reproduce.** It requires modelling UCC's exact compile-time `FName` interning order
  for new member names — an internal encoder artifact, not derivable from the trunk. (Import/export
  order WAS reproduced; name order for members resisted a corpus reconstruction and a qsort
  inversion — see board finding `uscript-name-table-member-fname-order`.)

## Proposal
Treat name-table ORDER as an evidence-backed exclusion: the parity gate compares name-table CONTENT
(names + flags as a set) and canonicalises name references by string when comparing bodies (the
identity/permutation methodology `NATIVE-MATERIALIZE.md` already prescribes), so a member-bearing
class counts as byte-exact when everything but name order matches. Keep striving to reproduce exact
order opportunistically. This is queued for the pre-merge Opus re-review.

## Answer

**Owner ruling (2026-09-05): do NOT exclude — REPRODUCE it.** "Strive for our algorithm to be on
par with UCC's. Don't do hacks just to satisfy a single package scenario." So name/import/export
table ORDER and FName CASE are no longer accepted exclusions: the compiler must reproduce UCC's real
ordering + casing algorithm corpus-wide. Plan: (1) build the global `FName` registration order =
intrinsic `EName` table (core.dll @0x10a778c) + each dependency package's name table appended in
package-LOAD order, deduped; (2) RE UCC's compile-time interning order for THIS package's new names
(class/member/local names — the encounter order during parse/compile); (3) gather in that global
index order and run the ported `msvc_qsort` (already in ordering.py) → exact name table; imports
likewise; FName case comes from the same global pool. Then `perm_gate`'s only remaining exclusion is
the per-build-random GUID (i.e. `perm_gate` collapses toward the strict `gate`). Tracked as the
name-table-ordering true-parity RE (runs after the conversation emitter frees `compile.py`).

