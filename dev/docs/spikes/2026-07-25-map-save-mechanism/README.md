# How `MAP SAVE` writes a package, and what a waiter can conclude from the bytes

**Date:** 2026-07-25 · **Substrate:** the committed `uned/UED22/core.dll` (UnrealEd 2.2 for Deus Ex)
· **Harnesses:** [`extract_save_mechanism.py`](extract_save_mechanism.py),
[`measure_header_window.py`](measure_header_window.py)
· **Pinned by:** `uedctl/tests/test_engine_facts.py::test_save_package_writes_a_temp_and_moves_it_and_never_reads_a_file_through_its_imports`
· **Consumers:** `driver.map_save` / `driver.package_header_problem`, `unrealed/commands.md`
"`MAP SAVE` writes `Save.tmp`", `decisions.md` 2026-07-25 11:31 UTC (+ its two corrections)

## Why the question came up

`MAP SAVE` answers nothing over the console, so the only evidence a save happened is the file. The
old wait rule ("size non-zero and equal across two polls") could not tell a *finished* file from a
*stalled* one, and the proposed fix — check the written package's header — is only worth its
complexity if a half-written file can actually appear at the destination. That depends entirely on
how the editor writes it.

## Q1 — What `UObject::SavePackage` does (📖 string table, order inferred)

`extract_save_mechanism.py` finds these UTF-16 literals at consecutive offsets in `core.dll`:

| offset     | literal |
|------------|---|
| `0x9e0e0`  | `UObject::SavePackage` |
| `0x9e270`  | `SaveExports` |
| `0x9e288`  | `SaveImportMap` |
| `0x9e2a4`  | `SaveExportMap` |
| `0x9e2c0`  | `RewriteSummary` |
| `0x9e2f4`  | `Save.tmp` |
| `0x9e520`  | `Moving '%s' to '%s'` |

Read as the phase sequence it plainly is: the package is serialized into a **temp file**, its
**summary — the 36-byte header carrying every object table's count and file offset — is rewritten
LAST**, inside that temp, and only then is the temp **moved** onto the destination path.

**Confidence 📖, not ✅.** What was observed is that the literals sit in that order in the string
table; the control flow is inferred from it. Two things follow that a waiter must respect:

- A crash mid-serialize leaves the destination **absent, or the PREVIOUS file untouched** — still
  complete, still carrying its old mtime. So "a file is there" is not evidence of this save; a wait
  has to compare against a **pre-save stat**.
- `Save.tmp` is a **fixed name**. Where it is created is *not* in the string table (the literal is a
  bare filename) — see the open `board/inbox.md` spike.

## Q2 — Is the move a rename or a byte copy? **Unknowable from the binary's imports**

This is the half that produced a retraction, so it is written out in full.

`core.dll` imports **no** `MoveFileW`/`MoveFileExW`/`CopyFileW`/`CopyFileExW`. It is tempting — and
an earlier revision of `decisions.md` did exactly this — to conclude "therefore the move must be a
hand-rolled read/write copy, therefore a truncated destination is reachable, therefore the header
check has a demonstrated failure mode to catch."

**That inference is invalid.** The same import table also contains **no `ReadFile`**, and no
file-mapping API (`CreateFileMappingW`/`MapViewOfFile`) — yet `core.dll` demonstrably *reads*
packages, which is most of what it does. Its file I/O therefore does not go through its import table
at all (it imports `GetProcAddress`/`LoadLibrary*`), and the absence of `MoveFile*` says nothing
whatsoever. Its actual file-API imports are `CreateFileW`, `WriteFile`, `SetFilePointerEx`,
`FlushFileBuffers`, `GetFileInformationByHandle`, `GetFileType`, plus the
`FindFirstFileExW`/`FindNextFileW` directory walk.

**Status: undetermined.** If the move is atomic, a truncated file can never appear at the
destination and the header check is pure insurance. If it is a copy, a wedge mid-copy leaves a valid
header over too few bytes, which the check catches. **No truncated destination has ever been
observed** — the one historical report ("a truncated `Leaves` array captured from a half-written
`.dx`") was retracted by `spikes/2026-07-15-native-materialize/sections/91-leaves-overproduction.md`,
which rebuilt the same golden behind a far more generous idle barrier and got a byte-identical Model
body. Settling it needs a live probe (watch the destination's size/inode during a big save) — filed
on `board/inbox.md` together with the `Save.tmp` location question.

## Q3 — How much can a header check actually vouch for?

`measure_header_window.py` walks every package the real composed search path resolves (264 files:
120 `.dx`, 60 `.utx`, 47 `.u`, 35 `.umx`, 2 `.uax`; 242 at version 68, 18 at 69, 4 at 61) and
computes how far into the file the header's own claims reach.

| rule | maps (`.dx`, n=120) | median |
|-------------------------------|---------------------|---|
| offsets inside the file only  | 92.0 – 99.0 %       | 98.2 % |
| **+ room for the declared entry counts** | **98.3 – 99.7 %** | **99.5 %** |

So requiring each table to have room for `count` entries at their minimum encoded size moves the
worst-case vouched-for fraction from ~92 % to ~98 % of a map. **It does not close the window**: a
write that died in the last ~1.7 % of a map still passes. Closing it needs a full table parse, which
needs the bytes on the host.

The per-entry minimums (name 5, import 7, export 12) are strict lower bounds derived from
`upackage._parse_package`'s field order — note `read_name` has **two** forms and 5 is the smaller
(`version < 64`: NUL-terminated string + u32 flags), which is why 5 and not 6. Every one of the 264
packages passes the check, the tightest margin being 4 bytes (`Quotes_Music.umx`).

## What was built on this

`driver.map_save` accepts a save only when the file **changed** since a pre-save stat, held a stable
size across N reads spanning a settle window, **and** its header describes a complete package —
with the header verdict cached per size for a bounded time rather than permanently, precisely
because Q2 is undetermined and a destination header cannot be assumed immutable once written.
