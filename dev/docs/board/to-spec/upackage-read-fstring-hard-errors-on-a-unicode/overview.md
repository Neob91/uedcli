+++
priority = "p2"
kind = "chore"
summary = "`upackage.read_fstring` hard-errors on a Unicode (negative-length) FString"
+++

# `upackage.read_fstring` hard-errors on a Unicode (negative-length) FString

—
found while running `event graph` on retail maps (2026-07-19). `load_package` on
`Maps/20_AireGardens.dx` (v69, UED22-written) dies with `FString overruns buffer (len=-66 at
2305)`, taking the WHOLE package down. Root cause: UE stores a Unicode string/name with a
**negative** length prefix (abs value = UTF-16LE char count, 2 bytes/char); `read_fstring`
(`upackage.py:56`) treats any `length < 0` as a hard `SchemaError` instead of decoding UTF-16. The
offending name-table entry decodes (UTF-16LE) to `'gardens,gardens_shared,gardens_corridor_1,
gardens_lights,tmp_mig储'` — a long comma-joined multi-**Group** value whose trailing non-ASCII
char (`储`) is what forced UED to pick the Unicode encoding (Andrzej's "exceeded Group size / not
a hard error" hunch — it IS a Group value, ~66 chars; the actual trigger is the non-ASCII →
Unicode path, not a length cap). **Fix:** in `read_fstring`, when `length < 0` read `abs(length)`
UTF-16LE code units and `.decode('utf-16-le')` (the standard UE convention) — this is the
low-level shared reader, so it fixes offline loading of EVERY package with a non-ASCII name/string
(textures, schema, the actor decode `event graph` needs). Keep the hard error for a genuinely
malformed length; a valid Unicode string must load. Add a regression (synthetic bytes or a small
committed package with a Unicode name). NB the `_read_name_v61` path may need the same treatment.
