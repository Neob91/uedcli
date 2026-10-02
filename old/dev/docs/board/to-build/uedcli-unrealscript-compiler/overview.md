+++
priority = "p1"
kind = "implement"
summary = "uedcli compiles UnrealScript to .u byte-identical to UED22 UCC.exe"
+++

# uedcli UnrealScript compiler — byte parity with UCC.exe

Make `uedcli` compile UnrealScript source into `.u` packages byte-identical to UED22's
`UCC.exe make`, reusing the byte-exact UE1 package serializer from native-materialize.

Owner decisions (2026-09-04):
- **Parity bar**: byte-identical; exceptions only when functionally *completely* inconsequential
  AND very hard to reproduce (closed, evidence-backed exclusion set — same discipline as
  `NATIVE-MATERIALIZE.md`). Nothing dropped silently.
- **Finish line**: keep going until **30 real packages** (Unreal stock + community) are byte-exact
  vs UCC; stop early only if parity is genuinely unreachable, and report why.
- **Scope**: full language including `#exec` asset imports.
- **Substrate**: Rust core in `uedcli-native` + Python bridge + CLI verb.

Reference recipe (owner's test): decompile a real `.u` to `.uc` with `ucc batchexport`, then compile
that `.uc` via **both** UCC and uedcli; the two outputs must match under the parity gate. UCC's own
compile is the golden — decompiler fidelity never enters the comparison.

RE knowledge lives ONLY in `dev/docs/unrealed/unrealscript/`. Spec + plan beside this file.

**Merge gate (owner, 2026-09-04):** before any squash-merge, an adversarial Opus (`claude-opus-4-8`)
review must re-check every RE conclusion (appStrCrc, table ordering, flag rules, defaults rule,
bytecode, the GUID-only exclusion set) and every byte-parity claim — try to refute, not confirm.
