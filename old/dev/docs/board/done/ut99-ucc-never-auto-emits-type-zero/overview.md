+++
priority = "p2"
kind = "finding"
summary = "UT99 UCC never auto-emits type-zero defaultproperties tags (UED22-derived rule is wrong for this substrate)"
+++

# UT99 UCC never auto-emits type-zero defaultproperties tags

Found compiling real `UWeb` (the last UT99 corpus target, `USCRIPT-COMPILER.md`'s "Real UWeb"
entry) after closing the two prior blockers (`pointer` var type,
`dev/docs/board/inbox/uscript-pointer-var-type-not-supported/`; explicit `Foo=None` object default,
`dev/docs/board/inbox/uscript-explicit-none-object-default-not/` — both now fixed, see
`USCRIPT-COMPILER.md`). With those two fixed, real `UWeb` compiles end-to-end and `perm_gate` finds
exactly ONE remaining divergence across all 7 classes: `WebApplication`'s class body emits 3 default
tags (`Level=None`, `WebServer=None`, `Path=""`) that the fresh UT99 UCC golden does not.

`compile-model.md`'s `defaultproperties` rule (`compile._auto_emit_defaults`) says a non-native,
non-transient class auto-emits a type-zero tag for every own property it doesn't explicitly set —
measured 2026-09-04 against controlled UED22 fixtures (`UscHello`/`UscVars`) and already pinned by a
UED22 corpus fixture (`NoSpuriousPkgImport`/`NSPIOne`: `var LevelInfo Level;` + empty
`defaultproperties{}` → golden DOES emit `Level=None`).

**`WebApplication` is plain (non-native, no `transient`) and has the identical shape** — `var
LevelInfo Level; var WebServer WebServer; var string Path;` + an empty `defaultproperties{}` block —
yet the fresh UT99 golden emits NOTHING for any of the three.

## Root-caused: a genuine UED22-vs-UT99 substrate difference, not a WebApplication quirk

Isolated with 5 minimal classes compiled fresh through UT99's own `UCC.exe` (not UED22's), all in
`_scratch/` (not committed — reproducible from this item):

- `UDPOne` (`var LevelInfo Level;` + empty `defaultproperties{}`, the exact `NSPIOne` shape) → **no
  tag emitted.** Same shape, UED22 emits one — this alone proves it's substrate-specific, not
  WebApplication-specific.
- `UDPTwo`/`UDPThree` (3 properties incl. an in-package object type, plus body-less functions before
  `defaultproperties`, mirroring `WebApplication` exactly) → no tags.
- `UDPScalar` (`var int N; var float F; var bool B;` + empty block) → no tags. Rules out "only
  object/string types are exempt" — UT99 skips ALL types.
- `UDPNoBlock` (`var int N; var LevelInfo Level;`, NO `defaultproperties` block at all) → no tags —
  rules out "an explicit empty block suppresses it" as the trigger too.

**Conclusion: UT99's own `UCC.exe` never auto-emits a type-zero defaultproperties tag for a plain
class's unset own property, regardless of type, count, or whether the source has an explicit empty
`defaultproperties{}` block.** The UED22-measured rule (`_auto_emit_defaults` returning `True` for a
non-native/non-transient class) does not hold for the UT99 substrate at all — UT99 behaves as if
EVERY class were explicit-only defaults, not just native/transient ones.

This is plausibly a real UCC.exe behavior change between the Deus Ex (UED22, older/patched) build and
UT99's later build, not a bug in the RE work — the two substrates already have known independent
differences (own `Core.u`, own name pool, `Fire`'s compact-index-width gap). Unconfirmed why; not
investigated further (would need a DLL diff or another live capture, out of scope for this pass).

## Proposed fix (not applied — flagging per project convention, not applying without a yes)

`_auto_emit_defaults(decl, class_flags)` needs to know which substrate it's compiling for and behave
differently: UED22 keeps today's rule (native/transient → explicit-only, else auto-zero); UT99 should
always be explicit-only (return `False` unconditionally, or at least whenever compiling under the
UT99 substrate). The compiler currently has no first-class "which substrate" input to `compile.py`
(`InstallEnv` just holds search dirs) — plumbing that through cleanly is the real work, not a one-line
guess, so it wasn't done as an in-scope fix here.

## Impact if fixed

This is the ONLY remaining divergence blocking `UWeb`'s 6-non-trivial-class perm_gate: all of
`WebResponse`/`WebRequest`/`WebServer`/`WebConnection`/`ImageServer`/`HelloWeb` and the whole rest of
`WebApplication` already identity-match. Fixing this would very likely take real `UWeb` to full
`perm_gate` byte-exactness (and worth re-checking the strict `gate()` too) — a genuine 7-class corpus
win toward the 30-package campaign target.

## FIXED 2026-09-13

Re-verified the claim fresh (live UT99 container, `UDPOne`/`UDPScalar`-shaped classes plus a fresh
`UWeb` decompile+recompile): our OLD rule fails `perm_gate` against the fresh golden every time;
substrate-gated, it passes. `InstallEnv` gained `substrate: str = "ued22"` (`"ued22"`/`"ut99"`,
validated); `_auto_emit_defaults(decl, class_flags, *, substrate)` returns `False` unconditionally
for `"ut99"`, unchanged for `"ued22"`. Threaded via the `env` already in scope at both call sites
(`compile._compile_single`, `compile._build_class_unit`) — no other function grew a parameter. The
default keeps every existing UED22 `InstallEnv()` call site (the CLI, every other test) unchanged;
only `test_uscript_ut99.py`'s `_compile` helper passes `substrate="ut99"`.

Real `UWeb` (all 7 classes) now matches a fresh UT99 golden byte-for-byte at `perm_gate` — the
corpus win. Strict `gate()` still fails on name-table ORDER, the same pre-existing UT99
own-name-pool gap already noted for `Fire` (not new; UT99 needs its own `ENGINE_NAME_POOL`/
`HIGHLIGHT_NAME_POOL` extraction, not attempted here). Pinned by two committed, live-UT99-UCC-verified
fixtures in `test_uscript_ut99.py`: `UscAutoEmitDefaultsUT99` (controlled — one class, an object +
every scalar type, explicit empty block) and `UWeb` itself (`fixtures/uscript/ut99/UWeb/`). Full
offline + integration uscript suites re-verified green, including every previously byte-exact UED22
package individually — the `substrate` default means none of their results moved.

The CLI (`cli/commands/uscript.py`) has no `--substrate` flag and always builds `InstallEnv` at the
default (`"ued22"`) — out of scope here, flagged in `USCRIPT-COMPILER.md` rather than silently added.

Detail: `USCRIPT-COMPILER.md`'s "Real UWeb" entry, `dev/docs/unrealed/unrealscript/compile-model.md`'s
`defaultproperties block` section.
