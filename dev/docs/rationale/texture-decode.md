# texture-decode — why `utexture.py` reads pixels the way it does

The agent-side engineering choices behind the native UE1 texture decoder. What the owner decided
about it — that the layout is derived from the data rather than a per-game table, that the format
code may only break ties and veto, and that an unresolvable BC2/BC3 file is an error rather than a
guess — lives in `../direction/`; this file holds the calls the implementation forced.

The measurements every entry cites are in
[`../spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md`](../spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md);
the format facts themselves are in [`../unrealed/package-format.md`](../unrealed/package-format.md).

## Detection and decodability are answered separately

"Which layout is this?" and "can we decode that layout?" are different questions, and merging them
makes the answer useless. A chain that fits `linear4` uniquely is identified; there is no verified
decoder for 4-bytes-per-pixel linear data. Keeping the two apart lets the error say "this is a 4
bytes/pixel linear texture and we have no verified decoder for it" instead of "unknown".
`detect_layout` is therefore pure and knows nothing about `_DECODERS`; the resolver asks the second
question afterwards.

**Rejected:** one function returning "the layout, if we can decode it" — the draft that did this
contradicted itself, claiming both that a unique fit always wins and that an unsampled slot yields
an error. Both are true, of different questions.

**Refs:** `uedcli/utexture.py` `detect_layout`, `_DECODERS`; `uedcli/tests/test_utexture_layout.py`.

## The parser reports body integrity; the resolver classifies it

`decode_texture` used to raise when a body did not end where the export table said. That put the
check ahead of everything, so no later logic could get in front of it without reopening the parser —
and it made two different conditions indistinguishable, because a procedural texture has both
zero-length mips and (for `FireTexture`) trailing `TArray<FSpark>` bytes. The parser now records
`trailing_bytes` and `no_mip_data` on every body and raises only where it genuinely cannot continue.
The integrity signal is preserved for every texture — including file-version 61, where the
body-to-EOF check is the only signal the format offers — and gains information (how many bytes were
left over), while classification moves to the layer whose job that is.

**Rejected:** weakening the guard so that it only raises when every mip is empty — that leaves every
other trailing-bytes shape unguarded on the v61 path, to make one fixture produce one case.

**Refs:** `uedcli/utexture.py` `TextureObj`, `_read_mip_array`, `TextureResolver._decode_export`.

## Array selection runs before detection, and never falls back on failure

A `UTexture` may carry two mip arrays, and which one is used has to be decided before anything looks
at pixel sizes — detection over an empty chain would index mip 0 of an empty list and raise, and no
Python exception may reach the user. So: an array carries data iff it is non-empty and at least one
mip has bytes; `Mips` wins if it carries data, else `CompMips`, else `no-mip-data` with detection
never invoked. "`Mips` is absent" is deliberately not a concept — a zero-length array and an
all-empty one are one rule.

The fallback fires only on that rule. A `Mips` array that carries data and then errors reports its
error.

**Rejected:** falling back to `CompMips` whenever `Mips` fails to decode — it papers a real
corruption over with a lossy copy, and it makes the result's provenance unreadable: a caller could
no longer tell whether `array == "comp-mips"` meant "there was no original" or "the original was
broken". Measured cost of the strict rule: zero, since all 69 `bHasComp` textures have a perfectly
decodable P8 `Mips`.

**Refs:** `uedcli/utexture.py` `_decode_export`; `uedcli/tests/test_utexture_blocks.py`.

## Each mip array is judged against its own format code

`Format` describes `Mips` and `CompFormat` describes `CompMips`, and the two arrays hold different
layouts by construction — all 69 measured `CompMips` arrays are block compressed while their `Mips`
are P8. `detect_layout` therefore takes the code as an explicit argument rather than reaching into
the texture, so there is no way to judge one array by the other's code. Doing so would send every
one of the 69 textures this work exists to fix down an error branch.

**Refs:** `uedcli/utexture.py` `detect_layout` signature; the two-arrays-two-layouts test in
`uedcli/tests/test_utexture_blocks.py`.

## The result is a typed union, and its error object is deliberately truthy

`resolve()` returned `None` for a bare ref, an absent package, a corrupt file, an unknown name and
an undecodable layout alike, so no caller could tell which — and the fixes differ. It now returns a
`DecodedTexture` or a `TextureError` naming one of twelve cases — four about the ref (fixed by
writing a different ref) and eight about the decode (fixed by getting a different file).

The error is left truthy on purpose. Callers written against the old contract say `if got:`, and a
falsy error would let every one of them keep "working" while silently rendering an error object as a
picture. Truthy makes the migration a visible failure. Both committed mesh harnesses had exactly
that bug latent in them.

**Rejected:** giving `TextureError` a `__bool__` returning `False` — convenient, and it hides the
one class of defect the type change exists to surface.

**Rejected:** deferring the four ref-layer cases to the asset catalog — four committed tests already
assert `resolve(...) is None` for them, so they would have been left with no defined expectation the
moment the return type changed.

**Refs:** `uedcli/utexture.py` `TextureError`; the two harnesses under
`../spikes/2026-07-25-native-mesh-decode/harness/`.

## Results are cached by identity, errors included

A committed test asserts `resolve(x) is resolve(x)`, and callers hold the result and compare it. An
equal-but-rebuilt object would also re-decode every mip. Caching errors too means a package that
will not open is opened once, not once per reference into it.

**Refs:** `uedcli/utexture.py` `TextureResolver.resolve`.

## The mip pyramid is a lazy property, not an eager field and not a second entry point

A caller that picks a mip from screen density needs every level; the callers that only ever draw
level 0 must not pay for the rest. A full pyramid is about a third more work and memory than mip 0
alone, so `mips` decodes on first access and caches on the instance.

**Rejected:** a separate `resolve_mips(ref)` accessor — it would have to return the same object from
the same cache entry, which makes it a pure alias: a second way to ask one question, the same
argument that ruled out a `texture_has_bMasked()` predicate.

**Rejected:** decoding every level eagerly — simpler, but it taxes every existing caller for a
feature none of them uses yet.

**Refs:** `uedcli/utexture.py` `DecodedTexture.mips`.

## Class defaults are resolved for the flags, and "unknown" is `None` rather than `False`

The owner ruled that `bMasked` is read as the export's tag if present, else the resolved class
default. Resolving one means walking the class's ancestor chain through the code packages on the
search path, which is memoised per resolver and per class because the walk decodes whole `.u`
packages and every texture in a package shares the answer.

On a path with no code package neither branch of the rule applies, so the flag reports `None`. That
is the "read any texture from any engine" case — a lone `.utx` — and reporting `False` would be
reporting a value nothing supplied. It is a provisional call, parked on the board with its known
cost (a caller that ORs the flag treats `None` as falsy).

**Refs:** `uedcli/utexture.py` `TextureResolver._effective_flag`, `_class_defaults`; board item
`bmasked-with-no-reachable-class-default-source`.

## The decoder reports `bMasked`/`bAlphaTexture` and never applies them

The transparency mask comes only from the pixel data — palette index 0 for P8, the punch-through
bit for BC1, the block's alpha for BC2/BC3. Those bits are literally in the file; `bMasked` and
`bAlphaTexture` are engine render policy, owned by whoever is drawing. Folding them in would make
identical bytes decode to two different images depending on a flag the pixel layer does not own, and
discarding stored alpha because a flag is unset is data loss the caller cannot undo. `Engine.Texture`
defaults both to `False`, so gating on them would have switched block alpha off corpus-wide.

**Refs:** `uedcli/utexture.py` `DecodedTexture`; the consumer's own OR, recorded in board item
`four-actor-preview-faces-rulings-need-a-durable`.

## The mask stays binary, and the loss is recorded rather than fixed here

`mask` is one byte per texel, 1 or 0, which is what every caller already reads. BC2/BC3 carry a real
per-texel alpha value, and it is thresholded at zero. Widening the field would silently change the
meaning of something existing callers consume — they test it for truthiness, so they would keep
working by accident while the contract changed underneath them.

**Rejected:** widening `mask` to 0..255 inside the slice that added two pixel formats — the right
change, at the wrong moment, with no caller needing it yet. Measured scope of the loss today: zero.

**Refs:** board item `bc2-bc3-graded-alpha-is-flattened-to-a-binary`.

## Hostile input is capped, not trusted

A package is untrusted input, and every count in it is a raw integer that some other program wrote.
Three layers, because they fail differently:

- **The header's table counts** are bounded by the file's own length, before a single entry is
  read. No table entry can occupy fewer than one byte, so an N-byte file cannot hold more than N
  of anything — an exact bound needing no magic number. This one is not optional politeness: a
  name's length is a signed compact index, so a negative one moves the read cursor backwards, and
  negative indices into `bytes` are legal in Python, so the walk cycles inside the buffer instead
  of running off the end. Measured before the bound: a declared count of `0xFFFFFFFF` ran over
  200 s inside a 2.5 GB cap without returning. A negative name length is refused outright for the
  same reason.
- **The mip declarations** are capped at 32 mips, 65536 px per side and 256 MB per mip, and no mip
  may run past the end of the file. Far above anything real — the largest texture measured
  anywhere is 2048×2048 with 12 mips.
- **A structural backstop** on `resolve()` and `exists()` catches whatever still gets through,
  because the header tables are not range-checked at load and the lookup walk reads several
  indices out of them. `resolve` reports `package-unreadable`; `exists` contributes nothing rather
  than false-rejecting a ref the engine would accept.

The first layer is the one a test must check for time, not just for "no exception" — a hang
satisfies "no exception" perfectly.

**Refs:** `uedcli/utexture.py` `load_package`, `MAX_MIPS`, `MAX_MIP_DIM`, `MAX_MIP_BYTES`,
`TextureResolver.resolve`.

## The sweep has its own export matcher, and production stays exact-match

The shipped `textures()` matches `class == "Texture"` exactly, so `FireTexture` and friends are
never listed through it. Widening that belongs to the asset catalog, which is what needs to
enumerate every texture-ish object. The corpus sweep needs the wider set to assert what the
procedural classes do, so it defines its own matcher and asserts separately that production has not
been widened.

**Refs:** `uedcli/tests/test_utexture_corpus.py` `_texture_like`.

## The offline fixture's payload is ours, but its encoders are not

A synthesized fixture only proves the decoder agrees with our own encoder — it passes just as
happily when both are wrong the same way. The independence that makes the cross-check evidence comes
from the encoder being outside our control, not from the artwork being someone else's. So
`UccCompMips.utx` carries our own generated artwork, with its P8 mip chain built by the game's own
`ucc make` and its DXT1 blocks written by Pillow; only the container is ours. The assembly step is a
hand-run script whose output is committed, so no test needs wine.

**Rejected:** committing a real game texture — strongest technically, and it redistributes
copyrighted content the ignore rules exist to keep out.

**Rejected:** our own artwork through our own compressor — no copyrighted bytes, and it compares our
compressor against our decompressor, passing when both are wrong the same way.

**Rejected:** rebuilding the fixture in a test — same circularity, one layer up.

**Refs:** `uedcli/tests/build_uccfixture.py`;
[`../spikes/2026-07-26-ucc-texture-fixture/findings.md`](../spikes/2026-07-26-ucc-texture-fixture/findings.md).

## The agreement tolerance is not the correctness check

Comparing our BC1 decode against the P8 copy of the same picture (mean absolute channel error ≤
8/255, measured 2.831) separates layout and endpoint errors by 14–35×. It does not separate an
index-decoding error at all: an index bit-offset off by one scores 4.801 and passes, because shifted
index bits still select from the same four per-block colours. The load-bearing check is therefore
byte-exactness against Pillow's DDS decoder, whose conventions are pinned first (bit-replicated
RGB565, integer thirds). The tolerance is also valid at mip 0 only — below 16×16 a correct decode
diverges, because the downsampled image carries detail under the 4×4 block size.

**Rejected:** describing the tolerance as "the decode is correct" — it was, and it is false.

**Refs:** `uedcli/tests/test_utexture_blocks.py`;
[`../spikes/2026-07-26-ucc-texture-fixture/findings.md`](../spikes/2026-07-26-ucc-texture-fixture/findings.md) §5–6.
