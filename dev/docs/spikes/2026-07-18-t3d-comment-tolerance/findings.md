# T3D import: comment & unknown-property tolerance — findings

**Date:** 2026-07-18
**Question:** Does UnrealEd's T3D **import** parser tolerate comments (does it *strip* them, or
*error* on them)? — asked to decide how the `folder` concept can ride `actor show` output through
`actor show | actor add -` while the same text stays importable by UnrealEd.
**Method:** two independent tracks, run in parallel — (A) static disassembly of the UED22 binaries
and (B) a live `MAP IMPORTADD` probe. They **agree at the instruction level**.

## Answer

**UnrealEd's T3D importer silently STRIPS `//` line-comments; it does not error on them.** `/* */`
and `;` are not comment syntax (they only survive incidentally, as a no-`=` line that gets skipped).
An unknown property warns and is skipped, import continues. Nothing here crashes or aborts the import.

| Input on an actor-property line | Import | Editor log | Verdict |
|---|---|---|---|
| `//` line-comment | ✅ actor imports | silent | **true comment — stripped** |
| `/* … */` (single line) | ✅ imports | silent | survives only as a no-`=` skipped line (fragile) |
| `;` semicolon | ✅ imports | silent | survives only as a no-`=` skipped line (fragile) |
| unknown prop `Foo="…"` (>64-char value) | ✅ imports | `Warning: Unknown property in defaults` | warned + skipped, non-fatal |
| stray `//` before the block | ✅ imports | silent | stripped |

## Track A — static RE (byte-exact)
Full detail: [`RE-findings.md`](RE-findings.md). Chain: `ULevelFactory::FactoryCreateText`
(Editor.dll @0x58cb0) → `ImportProperties` (Editor.dll @0x75de0, passes `Exact=0`) →
`Core.dll ParseLine` (@0x57290). `ParseLine` @0x5730e compares the char to `/` (0x2f) and the next
char to `/`, and when both hit — **gated on not-in-quotes AND `Exact==0`** — latches a flag that
consumes but stops copying the rest of the line. There is **no** `*` (0x2a) or `;` (0x3b) handling,
so `/* */` and `;` are not comment tokens. Unknown property → `FindProperty` NULL →
`Logf(NAME_Warning, "%s: Unknown property in defaults: %s")` → continue. Harness: `harness/disasm.py`,
`harness/imports.py`.

## Track B — live probe (`MAP IMPORTADD`)
Harness: [`harness/probe.py`](harness/probe.py). Six one-actor `Light` T3D variants were imported
into ephemeral UED22 editors and re-exported. Every variant imported with the actor intact and the
editor alive; the carrier was never re-exported (UnrealEd doesn't store comments); only the unknown
property emitted a non-fatal `Warning: Engine.Light: Unknown property in defaults: UedcliFolder="…"`
(the >64-char value caused no problem — a StrProperty *value* has no FName length limit). This
matches Track A exactly: the `//`/`/* */`/`;` lines are silently absorbed; only a name-with-`=`
warns.

## Decision — the folder interchange carrier
Use a **bare `// uedcli-folder: <path>` line** as the on-the-wire form of an actor's folder:
- `actor show` emits it inside each actor block → the output **round-trips the folder** through
  uedcli's own parser (`actor add -`) AND stays **UnrealEd-importable** (the editor strips the `//`
  silently, no warning, no crash).
- Chosen over the unknown-property carrier (`UedcliFolder="…"`), which works but spams a per-actor
  `Unknown property in defaults` warning; and over `/* */`/`;`, which only survive incidentally.
- Constraints: the carrier must be a **bare** `//` line (never inside a quoted value — there `//` is
  preserved, not stripped); avoid `|` (a `ParseLine` line-terminator). The folder itself stays stored
  in the per-actor `folder` **sidecar**, never in the trunk `actor.t3d` body and never in the built
  map — the comment is purely the `show`/`add` interchange encoding.

Folds into: board item `actor-folders-hierarchical-actor-organization` (resolves review point R6 — `actor show`
default output is both importable and folder-carrying), and the durable engine fact in
`unrealed/t3d.md` "Comments & unknown properties on import".

## Pinned regression
`uedcli/tests/test_engine_facts.py::test_t3d_import_strips_double_slash_comments` asserts the unique
16-byte `//`-detect-and-latch pattern (`83fa2f 750f 66395102 b8010000000f44`) at `ParseLine` RVA
0x5730e in the committed `core.dll` — offline, no editor/capstone. A UED22 rebuild that changes the
comment-strip trips it.
