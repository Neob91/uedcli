"""Dump the TRUE runtime order UCC.exe interns new `FName`s during a live compile, by breaking on
every call to `AllocateNameEntry` (not `SavePackage` — that only gives the SAVE-time global index,
already covered by `dump_gobj.py`). This answers a different question: in what order does the
COMPILER itself first encounter each new identifier while parsing a `.uc` source, independent of the
later `SavePackage` sort. See `findings-ordering-re.md`'s "2026-09-13" section for the result and how
it fixed `ordering.name_creation_order`'s function-locals timing.

DISASSEMBLY (core.dll, ImageBase 0x10000000; `objdump -d -M intel`, cross-checked against the export
table — `objdump -p core.dll` — by NAME-POINTER-TABLE INDEX, not by the ordinal number printed next
to it: the `[Ordinal/Name Pointer] Table` and `Export Address Table` list entries in the SAME index
order, so `?Foo@@…` at name-table index N pairs with the address-table row whose FIRST bracket is
also N, not with the ordinal number in its `+base[...]` column):

  FName::FName(const TCHAR*, EFindName)   @ 0x1005cad0  (`??0FName@@QAE@PBGW4EFindName@@@Z`)
    - if the string is empty, sets Index=0 (None) and returns.
    - hashes the string (`appStrihash`-style, case-insensitive) into a 4096-bucket table at
      0x100f0de0 and walks the bucket's linked list comparing `FNameEntry` strings case-insensitively.
    - on a match: copies the existing Index; if `FindType==FNAME_Intern` (2), ALSO OR's `RF_Native`
      (0x4000000) onto the existing entry's flags (matches "Intern" registering the engine boot pool).
    - on FindType==FNAME_Find (0) and no match: Index=0 (None), return (no allocation).
    - on FindType==FNAME_Add (1) or FNAME_Intern (2) and no match: pops a freed slot from the
      `Available` TArray (0x10138e50 data / 0x10138e54 count) if any, else appends a new slot to the
      SAME global array `dump_gobj.py` calls `GObjNames` (0x10139d50) via `TArray::AddZeroed`
      (0x1001a9b0) — confirms this constructor's Names array IS `GObjNames`. Then calls:
  AllocateNameEntry(const TCHAR* Name, DWORD Index, DWORD Flags, FNameEntry* HashNext)  @ 0x1005cdc0
    - cdecl, 4 pushed args (`Name, Index, Flags, HashNext`) then `call; add esp,0x10` — this is the
      ONLY call site that allocates a genuinely NEW `FNameEntry`. Breaking here and reading
      `*(int*)($esp+4)` (the `Name` arg, a UTF-16LE C string) at each hit gives exactly the sequence
      of first-time name registrations, in true call order — the compiler's own parse-order encounter
      sequence, not a save-time sort artifact.

METHOD (winedbg, piped stdin): unlike `dump_gobj.py`'s SavePackage probe (a ONE-SHOT breakpoint that
never needs to resume correctly, since the process is about to end), this needs MANY hits across one
compile, so it uses winedbg's own `break *ADDR` (which manages the INT3 restore/step/re-arm dance
correctly across repeated hits) instead of a raw one-shot memory-patched INT3. A single batch script
of `cont` + `x/64b *(int*)($esp+4)` pairs, repeated enough times to cover the whole boot+load+compile
(a few thousand for the UED22 substrate's stock EditPackages set), is piped to ONE `winedbg UCC.exe
make` invocation; parse the interleaved hex dumps back into UTF-16LE strings.

Run in the `ued-x86-runtime` build image (wine-8.0 + winedbg + python3), against a container with the
target package's `.uc` sources already placed under `/opt/<Package>/Classes/` and `EditPackages=
<Package>` in `unrealtournament.ini` (this repo's baked UED22 substrate image already has the
`realpkg` corpus fixtures wired into `EditPackages`, including `DavesBrushBuilders`):

    python3 dump_name_creation_order.py --container uned-re --package DavesBrushBuilders --hits 6400

`--hits` must comfortably exceed the package's OWN new-name count plus everything registered before
it in the ini's `EditPackages` list (boot intrinsics + every earlier package's own names) — the
2026-09-13 DavesBrushBuilders run needed ~6233 of 6400 planned hits; pass a comfortable margin and let
it finish (there is no live way to know the count in advance without a first over-provisioned run).
This is exploratory RE tooling, not a repo-wide regression: it takes several minutes per run and is
not part of `bin/test`. Findings it produces get pinned as regular pytest assertions elsewhere (see
`test_uscript_realpkg.py::test_davesbrushbuilders_locals_register_inline_not_deferred`).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

_ALLOC_NAME_ENTRY = "0x1005cdc0"   # core.dll VA of AllocateNameEntry (see docstring)


def _sh(container: str, script: str, *, inp: str | None = None, timeout: int = 1200) -> str:
    return subprocess.run(["docker", "exec", "-i", container, "sh", "-c", script],
                          capture_output=True, text=True, timeout=timeout, input=inp).stdout


def _setup_package(container: str, package: str) -> None:
    """Clear any stale build output for `package` (its `.uc` sources + `EditPackages` entry are
    assumed already present — this repo's baked UED22 image wires the `realpkg` corpus in)."""
    _sh(container, f"rm -f /opt/UED22/{package}.u")


def _build_batch(hits: int) -> str:
    lines = [f"break *{_ALLOC_NAME_ENTRY}"]
    for _ in range(hits):
        lines.append("cont")
        lines.append("x/64b *(int*)($esp+4)")
    lines.append("quit")
    lines.append("")
    return "\n".join(lines)


def _run(container: str, batch: str) -> str:
    _sh(container, "mkdir -p /re")
    _sh(container, "cat > /re/batch_names.txt", inp=batch)
    return _sh(container,
              "cd /opt/UED22 && WINEPREFIX=/wineprefix WINEDEBUG=-all "
              "winedbg UCC.exe make < /re/batch_names.txt")


_LINE_RE = re.compile(r'0x[0-9a-f]+(?: core\+0x[0-9a-f]+)?:\s+([0-9a-f ]+)$')


def parse(raw: str) -> list[str]:
    """Split winedbg's output into one byte-blob per breakpoint hit and decode each as UTF-16LE."""
    groups: list[list[int]] = []
    cur: list[int] = []
    started = False
    for line in raw.splitlines():
        if 'Stopped on breakpoint' in line or line.strip().startswith('Breakpoint 1 at'):
            if cur:
                groups.append(cur)
            cur, started = [], True
            continue
        m = _LINE_RE.search(line)
        if m and started:
            cur.extend(int(b, 16) for b in m.group(1).split())
    if cur:
        groups.append(cur)

    def decode(bs: list[int]) -> str:
        out, i = [], 0
        while i + 1 < len(bs):
            ch = bs[i] | (bs[i + 1] << 8)
            if ch == 0:
                break
            out.append(chr(ch))
            i += 2
        return "".join(out)

    return [decode(g) for g in groups]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--container", required=True, help="a running ued-x86-runtime container name")
    ap.add_argument("--package", required=True, help="EditPackages entry to dump names for")
    ap.add_argument("--hits", type=int, default=6400, help="breakpoint hits to plan for (over-provision)")
    args = ap.parse_args()

    _setup_package(args.container, args.package)
    raw = _run(args.container, _build_batch(args.hits))
    names = parse(raw)
    for i, n in enumerate(names):
        print(i, n)
    print(f"# {len(names)} names captured", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
