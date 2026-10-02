# On a genuinely undecodable UTF-16 unit, should `upackage.read_fstring` raise or substitute?

## Context

The fix decodes a negative-length FString as UTF-16LE. A valid Unicode string (the real case, a long
`Group` value) decodes cleanly either way; this only bites on a corrupt byte span that is not valid
UTF-16.

- **Strict (`errors="strict"`, raise `SchemaError`)** — matches uedcli's no-silent-halfanswer /
  no-fallback convention (`CLAUDE.md`; `direction/packages.md`): `upackage` is the model-side
  authority, and a corrupt package should exit 2 naming the file, not silently produce a
  mojibake string that flows into schema/compare.
- **Replace (`errors="replace"`)** — what the existing `native/codec.py` copy does. More tolerant;
  lets a package with one bad name still load. But it hides corruption as `�` in an otherwise
  authoritative read.

Recommendation: **strict** in `upackage` (raise `SchemaError`, keeping the offset/length in the
message), and leave `native/codec.py` on `replace` as its rendering-path choice — or align both to
strict when they unify. A valid Unicode name is unaffected; only real corruption changes disposition.

## Answer

<!-- Empty = open. -->
