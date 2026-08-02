+++
priority = "p2"
kind = "owner-question"
summary = "OWNER-GATED engine finding: record the .umx embedded-title offsets in dev/docs/unrealed/."
+++

# [OWNER] unrealed/: record the .umx embedded-title offsets

The audio arm's `.umx` title reader (`umxtitle.py`) rests on tracker-module header offsets — an
engine/format finding that belongs in `dev/docs/unrealed/` and should be back-referenced from the
code comment. `dev/docs/` is owner-gated. Proposed text below (new short doc, e.g.
`unrealed/umx-titles.md`, or a section in an existing audio doc — your call on placement).

## Proposed text

> ## `.umx` embedded module titles
>
> A `.umx` is a UE1 package wrapping one `Music` object whose body is a raw tracker module. The song
> title sits at a fixed offset from each format's magic; scan the whole file for the magic (the module
> is embedded inside the package body, not at offset 0):
>
> | format | magic               | title field            | confidence |
> |--------|---------------------|------------------------|------------|
> | IT     | `IMPM`              | 26 bytes at magic +4   | LIVE — all 35 Deus Ex `.umx` are IT; 3 golden titles verified (`Area51_Music`→"Area 51", `Credits_Music`→"The Illuminati", `Area51Bunker_Music`→"Begin the End") |
> | S3M    | `SCRM` (at +0x2C)   | 28 bytes at magic −0x2C | FIXTURE — format spec, not seen on DX |
> | XM     | `Extended Module: ` | 20 bytes at magic +17  | FIXTURE — format spec, not seen on DX |
>
> Read the title latin-1, NUL-terminated, stripped; an all-NUL field is an ABSENT title, reported as
> `null` with the format still named. An unrecognised container is `(None, "unknown")` — never a
> blank title that reads as "this module has no title". Implemented in `umxtitle.py`; the golden IT
> titles are pinned by `test_umxtitle.py`.
