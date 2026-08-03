+++
priority = "p2"
kind = "owner-question"
summary = "A provisional call: when no code package can supply Texture's defaults, b_masked reports None rather than false."
depends-on = ["native-texture-decode"]
+++

# `bMasked` with no reachable class-default source

> Migrated to `native-texture-decode`'s `questions/b-masked-no-class-default-source.md`. Kept here
> because this slug is cited from code, `rationale/`, and other board items.

**A provisional call made while building board item `native-texture-decode`, recorded so it is not
silently derived.** The owner may overrule it; the cost is one field.

## What `bMasked` is, and what was ruled

A UE1 texture records "import-time masked" as a bool property called `bMasked`. A masked texture draws
its palette-index-0 pixels as holes on any surface. **Owner ruling (2026-07-27):** the flag is read as
*the export's tag if present, ELSE the resolved class default* — never "absent means false". UE1 omits
a tagged property equal to the class default (live-verified, `dev/docs/unrealed/t3d.md` "Partial
struct/array property values"), so an absent tag means "equal to the default", and only the default
says whether that is false.

## The case the ruling does not cover

Resolving the default means walking the texture class's ancestor chain through the **code packages** on
the composed search path (`uprops.resolve_class_defaults`). On a path with no code package —
a lone `.utx` handed to the tool, which is exactly the "read any texture from any engine" case the
decoder exists to serve — there is no default to resolve, so neither branch of the rule applies.

## The provisional call

`DecodedTexture.b_masked` is **`None`** in that case, never `False`. Rationale: "don't know" is never
returned as `False` (`direction/conventions.md`'s predicate rule), and the ruling says the *default* is
the answer, not that its absence means false — so reporting `False` would be reporting a value nothing
supplied.

Known cost: the consumer code the sibling spec pins,
`masked = bool(flags & 0x2) or decoded[ref].b_masked` (board item
`four-actor-preview-faces-rulings-need-a-durable` §4.3a), treats `None` as falsy — so on such a path a
masked texture renders unmasked unless the surface flag is set. That is the same outcome as today, but
it is a silent one.

## The alternative, if the owner prefers it

Make it a named typed decode error (`masked-default-unresolved`) so the caller must say what to do,
consistent with "no silent half-answers". More correct, and it makes a decode fail on a path that has
no code packages — which would break `level preview --native` on a textures-only search path.
