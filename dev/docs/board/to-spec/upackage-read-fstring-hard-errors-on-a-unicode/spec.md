# Spec — `upackage.read_fstring` must decode a Unicode (negative-length) FString

## Goal

`upackage.read_fstring` hard-errors on any FString whose compact length is negative. In UE1 a
negative length means a UTF-16LE string (abs value = code-unit count). Decode it instead of raising,
so every offline package load that hits a non-ASCII name/string succeeds. One low-level fix repairs
every decoder built on the shared reader (names, schema, texture props, the actor decode `event
graph` needs).

## Current state

- `uedcli/upackage.py:56` `read_fstring`: `if length < 0 or pos + length > len(buf): raise
  SchemaError(...)`. A `length < 0` is treated as corruption, not Unicode.
- Crash reproduced by the finding: `load_package("Maps/20_AireGardens.dx")` (v69, UED22-written)
  dies with `FString overruns buffer (len=-66 at 2305)`, taking the whole package down. The
  name-table entry decodes (UTF-16LE) to a long comma-joined multi-`Group` value ending in a
  non-ASCII char (`储`), which is what forced UED to pick the Unicode encoding.
- The name table reaches `read_fstring` via `_parse_package.read_name` (`upackage.py:203-208`, the
  `version >= 64` branch). `StrProperty`/`NameProperty` value decode reaches it via `uprops.py:877`
  and `:1146`. All are fixed by the one change.
- **A correct reference already exists.** `uedcli/native/codec.py:121` `read_fstring` handles the
  negative case: `n = (-length) * 2; buf[pos:pos+n].decode("utf-16-le", "replace").split("\x00",1)[0]`.
  It is a second copy of the reader (its unification is board item
  `migrate-utexture-py-dxpkg-py-onto-the-unified`); after this fix the two agree, and it is the
  cross-check oracle for the test.

## Design

In `upackage.read_fstring`, split on the sign of `length`:

- `length >= 0` (unchanged): read `length` bytes, split at first NUL, decode latin-1.
- `length < 0`: read `n = (-length) * 2` bytes, `.decode("utf-16-le")`, split at first NUL char.
- Bounds check both forms against `len(buf)` before slicing (`pos + n > len(buf)` for the Unicode
  form) — the overrun guard must survive, only its byte count changes.

Behavior surface: none at the CLI. This is an internal decode fix; a package that previously exited
2 with `malformed package (FString overruns buffer ...)` now loads.

`_read_name_v61` / the `version < 64` name path (`upackage.py:204-206`): **investigated, no change
needed.** Pre-v64 packages store names as NUL-terminated ANSI with no length prefix, so the
negative-length Unicode form cannot occur there. State this in the code comment so it is not
re-flagged.

## Edge cases & errors

- `length == 0`: empty string, unchanged (falls in the `>= 0` branch).
- Odd/oversized negative length that overruns the buffer: still a `SchemaError` naming the length
  and offset — a genuinely malformed length must stay a hard error (the no-fallback contract).
- Undecodable UTF-16 code units inside a well-sized span: see the open question (strict vs replace).
  `native/codec.py` chose `errors="replace"`; the no-silent-halfanswer convention argues for strict
  in `upackage`, the model-side authority.

## Tests

- Regression in `uedcli/tests/test_upackage.py` (or the package-reader test module): synthetic bytes
  — a name/FString with a negative compact length whose UTF-16LE bytes decode to a known non-ASCII
  string (e.g. the `…tmp_mig储` value) — asserts `read_fstring` returns it and advances `pos` by
  `(-length)*2`.
- A malformed negative length that overruns still raises `SchemaError`.
- Cross-check: the same bytes through `native/codec.read_fstring` yield the identical string (pins
  the two copies equal until they unify).
- If a small committed package with a Unicode name is cheap to add, a `load_package` round-trip over
  it; otherwise the synthetic-bytes test is sufficient (no gitignored asset needed).

## Open questions

One real fork — decode strictness on genuinely corrupt UTF-16. See
`questions/utf16-decode-strict-vs-replace.md`.
