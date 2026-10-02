# On a search path with no code package, should `b_masked` be `None`, or a named decode error?

## Context

A provisional call made while building `native-texture-decode`, recorded so it is not silently
derived. The owner may overrule it; the cost is one field.

`bMasked` is a UE1 texture bool: a masked texture draws its palette-index-0 pixels as holes. Owner
ruling (2026-07-27): the flag is read as *the export's tag if present, ELSE the resolved class
default* — never "absent means false". UE1 omits a tagged property equal to the class default
(live-verified, `dev/docs/unrealed/t3d.md` "Partial struct/array property values"), so an absent tag
means "equal to the default", and only the default says whether that is false.

The case the ruling does not cover: resolving the default walks the texture class's ancestor chain
through the **code packages** on the search path (`uprops.resolve_class_defaults`). On a path with no
code package — a lone `.utx`, exactly the "read any texture from any engine" case the decoder serves
— there is no default, so neither branch applies.

The provisional call: `DecodedTexture.b_masked` is **`None`** in that case, never `False`.
Rationale: "don't know" is never returned as `False` (`direction/conventions.md`'s predicate rule),
and the ruling says the *default* is the answer, not that its absence means false.

Known cost: the consumer `masked = bool(flags & 0x2) or decoded[ref].b_masked`
(`four-actor-preview-faces-rulings-need-a-durable` §4.3a) treats `None` as falsy — so on such a path
a masked texture renders unmasked unless the surface flag is set. Same outcome as today, but silent.

Alternative, if the owner prefers: make it a named typed decode error
(`masked-default-unresolved`) so the caller must say what to do, consistent with "no silent
half-answers". More correct, but a decode then fails on any path with no code packages — which would
break `level preview --native` on a textures-only search path.

## Answer

<!-- Empty = open. Write the decision here. -->
