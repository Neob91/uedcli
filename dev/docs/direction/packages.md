# Packages — one package-format core

## What we want

All Unreal package files — `.u`, `.dx`, `.utx`, `.uax`, `.umx`, `.unr` — are **one on-disk
container format**: the same magic, header, name/import/export tables, and tagged-property encoding.
Version 68 (Deus Ex) and version 69 (UT-lineage) differ in what the classes *say*, not in how the
file is laid out.

### One low-level reader; per-use-case decoders on top

There is **exactly one** low-level reader (`upackage.py`). It owns the header, the FCompactIndex
variable-length integer, compact strings, the name/import/export tables, object-reference
qualification, and the UE1 tagged-property list. Everything else is a decoder layered on top:
class schema and defaults, textures, meshes, the import closure, native map-file decode.

**No use-case and no file extension reimplements the low-level parsing.** The private parser copies
that predate the core migrate onto it; none survives as a second parser.

### The file describes itself — never a per-game table

Layout is derived from the **data**, not from a table of what a particular game meant. This is what
makes uedcli a generic UnrealEngine-1 tool rather than a Deus Ex one: a decoder that needs a game's
own code package to read that game's asset cannot read a lone `.utx` from an engine we have never
seen.

- A **mesh's vertex stride** is read off the `Verts` TLazyArray's own skip offset — 8 bytes for
  Deus Ex's `int16` quad, 4 for stock Unreal's packed dword. One decoder, every substrate, no flag.
- A **texture's layout** is fitted from the mip chain, which is self-describing: block-compressed
  formats floor at one block while linear formats keep scaling, so the tail of the chain separates
  them. The numeric `Format` code is a **hint, a tiebreak and a veto** — never the authority.

The limit this leaves is stated wherever the universality claim is made — docs, error text, code
comment — never buried as a corner case: **a block-compressed 16-byte chain that no code resolves
does not decode.** BC2 and BC3 have identical block sizes and identical chains and differ only inside
the alpha half; nothing in the data separates them. A chain that fits **exactly one** layout decodes
— P8, or a block-compressed chain no other layout fits. A **code-less** chain that several layouts
fit is ambiguous: a 16-byte BC1 chain is indistinguishable from P8 (48 of 1137 in `uned/UED22`
resolve as P8), so it is a named error, not a guessed BC1.

### A package READ has the engine's semantics

- **An unset property resolves to its class default**, decoded offline from the game's own `.u` — a
  bytecode walk to the `UClass` tail defaults block — and to the type's **zero** value when the
  class states none. A read never reports "absent" for something the engine would resolve.
- **Reads hard-require the schema.** There is no degraded stored-only read when the game's packages
  are not resolvable; see [`conventions.md`](conventions.md) "No silent half-answers, and no
  fallbacks".
- **Property keys are normalized to the `.u` spelling** (`lightbrightness` → `LightBrightness`).
  The engine is case-insensitive here, so this is canonicalization for stable diffs and
  authoritative output, not correctness.

### The schema is the GAME's own packages, never the editor's stand-ins

A game's composed package paths have **two derived views**: the **analysis view** — the real game
`.u`, read model-side by the closure, the missing-check, qualification, and the class-property
schema, which is the authority — and the **editor-load view**, the v69 stubs and content mounts the
editor is given ([`containers.md`](containers.md)).

A stub is recompiled against UT's `Engine`/`Core`, so its inherited base-class properties are UT's,
not the game's. Reading one for schema would be subtly, invisibly wrong, so the schema **never**
consults the stub cache. The set of packages searched is the composed `paths` uedcli already
resolves ([`projects-and-config.md`](projects-and-config.md)) — never a second, hardcoded search
list that would drift from it and miss a project's own overriding classes.

### Meshes decode natively

The complete `UMesh`/`ULodMesh` body decodes in-process. Rendering a mesh — a catalog thumbnail, an
actor preview — is therefore **pure offline compute: no editor, no container, and no `umodel.exe`**,
which survives only inside the stub pipeline it already serves.

### Decoding is cheap on a cold process

Every `uedcli` invocation is a fresh cold process, so decoded package primitives are cached
per-package on disk, in the derivable, never-committed per-user cache, and invalidated when the
file changes. **A cache that cannot be written is a loud, actionable error** naming the directory —
never a swallowed failure, because a silently dead cache re-decodes everything on every run,
invisibly.

### A decode failure is a typed result; the CLI chooses the disposition

The decode layer reports *what* went wrong and lets the caller decide — the one calibrated place
where "cannot decode" does not mean "the command fails": a request for **one named asset** exits 2;
**enumeration** records the asset as undecodable and keeps listing; a **whole-scene preview**
degrades that one surface and warns.

Decode correctness is proven against **independent oracles** — data encoded by the original tools,
or a third-party decoder — never against a fixture our own encoder produced.

## Rejected

**One core**

- **Per-use-case or per-extension copies of the low-level parsing** — the state the core exists to
  end; every copy is a second thing to keep true against the same wire facts.
- **Migrating every decoder onto the core in the change that introduced it** — regression risk on
  two byte-validated decoders for no feature gain.
- **New code on the core with the existing property reader left on its own copy** — leaves the
  duplication exactly where it hurts most.

**Defaults and the schema source**

- **Parsing the shipped `.uc` `defaultproperties` text** — a second grammar, unverified for v68.
- **Spiking the route before choosing it** — the binary walker was chosen directly.
- **Parsing a v69 stub for schema** — recompiled against UT's `Engine`/`Core`, so its inherited base
  properties are UT's, not the game's.
- **Reusing the editor-load search dirs for schema** — they lead with the UT-lineage substrate and
  the stub cache: the wrong authority for the game's own classes.
- **A bespoke hardcoded schema search list** — drifts from the resolved package paths, cannot see a
  project's overlays, and re-entrenches a Deus Ex-specific path.
- **The UCC decompile as a runtime source or fallback** — it stays a cross-check oracle only.
- **Opaque-accept of an unknown property**, **graceful degradation when the schema cannot be
  built**, and **a `--force` bypass** — all three are the silent-wrong-answer failure the
  validation exists to kill.
- **Preserving the stored spelling of a property key on replace** — superseded by normalizing to
  the `.u` spelling.

**Texture layout**

- **Reading `ETextureFormat` out of each game's `Engine.u`** — it makes decoding depend on having
  that game's code package, so a lone `.utx` from an unknown engine would not decode, defeating the
  universality.
- **Hardcoding one game's format table** — measured wrong across installs: the same slot is 8
  bytes/pixel in one shipped game and 2 in another. A wrong table mis-slices real data and then
  emits a *bogus* size mismatch, turning an honest failure into a wrong diagnosis.
- **Implementing the unsampled linear layouts from their definitions** — no samples exist to verify
  against and the slot meanings disagree across installs, so a guess returns a plausible wrong
  image (swapped channels) instead of an error.
- **Assuming BC3 for a code-less 16-byte-block chain** — commoner, so often right, and silently
  unrecoverably wrong otherwise.
- **Decoding both ways and picking by "alpha plausibility"** — a heuristic dressed as a
  measurement, with no ground truth to validate it.
- **"Every decode failure exits non-zero"** — it would stop a whole preview because one odd texture
  exists, and contradicts an undecodable asset staying enumerable.
- **Shipping native decode for P8 only**, and **keeping the UCC-under-Wine exporter as the non-P8
  fallback** — the first ships a coverage regression on non-Deus-Ex substrates; the second keeps
  the container/Wine seam that dropping UCC exists to remove.
- **Proving the decoder with a fixture our own encoder produced** — it proves only self-agreement.

**Meshes**

- **Driving the original UnrealEd to render a mesh**, and **reverse-engineering the stub pipeline's
  `umodel.exe` export** — neither fallback is needed; the body decodes directly.

## Refs

`../unrealed/package-format.md` · `../architecture.md` "Class-property schema, DEFAULTS & the
`actor prop` verbs" · `../spikes/2026-06-26-class-property-extraction.md` ·
`../spikes/2026-07-25-native-mesh-decode/` · `../spikes/2026-06-28-deusex-vs-unreal-package-format/`
