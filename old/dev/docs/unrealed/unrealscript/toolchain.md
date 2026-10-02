# The reference toolchain — running UED22 `UCC.exe`

How to compile and decompile UnrealScript with the stock UED22 compiler, which is the golden we match
byte-for-byte. All facts here verified live 2026-09-04. Driver: `uedcli/uscript/reference.py`
(reuses `stub.py`'s container machinery).

## The build container

UED22 runs under wine in an ephemeral no-GUI container (`stub.ephemeral_build_container`,
`LAUNCH_UED=0`). The substrate is flat at **`/opt/UED22`** — `UCC.exe`, every stock `.u`
(`core.u`, `Engine.u`, …), and the inis all sit directly there. UCC's convention: the **System dir
is the CWD** and the **game root is its parent**, so with CWD `/opt/UED22` the game root is `/opt`.

- Engine is a **UnrealTournament build** (package version **69**). UCC reads
  **`/opt/UED22/unrealtournament.ini`** (bind-mounted read-write; `make` rewrites it).
- Package search path is `[Core.System] Paths` in that ini; stock `.u` on it resolve by bare name.

## Compile (`ucc make`)

Sources for package `Foo` go at **`/opt/Foo/Classes/*.uc`**; output lands at
**`/opt/UED22/Foo.u`**. Steps (see `reference.ucc_compile`):

1. Write the `.uc` files into `/opt/Foo/Classes/` (via `docker exec -i … sh -c 'cat > …'`;
   `docker cp` fails under rootless docker — it remounts binds read-only).
2. Add `EditPackages=Foo` **inside `[Editor.EditorEngine]`**, right after the last existing
   `EditPackages=` line (`stub.inject_edit_package`). Appended at EOF it is silently skipped.
3. `cd /opt/UED22 && wine UCC.exe make` — recompiles packages whose `Classes/` is newer/absent.

**Success gate:** exit 0 AND stdout contains `Success - 0 error(s)` AND the output `.u` is > 64 bytes
(a 64-byte `.u` is an empty/failed compile that can still exit 0 with a warning). A compile error
exits 1 with `Exiting due to error`. Full output also goes to `/opt/UED22/UCC.log`.

## Decompile (`ucc batchexport`)

`cd /opt/UED22 && wine UCC.exe batchexport <Pkg>.u class uc <Z:-outdir>` writes one `<ClassName>.uc`
per class. The outdir **must** be a `Z:\…` path (`Z:` = container `/`; use `driver.to_z_path`). A
bare package name resolves via `Paths`; an arbitrary `.u` is passed by its container path.

This is our decompiler for the corpus: extract a real `.u`'s source, then compile it via both UCC and
uedcli. UCC's own compile is the golden — decompiler fidelity never enters the comparison.

## Other commandlets

`ucc help` lists: `batchexport checksum checksumpackage compress conform datarip decompress
HelloWorld help make master masterserver mergedxt packageflag server updateserver updateumod`. No
`dumpint` (that is an editor console verb, not a commandlet). `conform existing.u old.u` rewrites a
package to be binary-compatible with an older one (regenerates matching GUIDs/indices) — not used
yet, but relevant if cross-build GUID stability is ever needed.
