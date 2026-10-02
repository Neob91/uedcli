+++
priority = "p3"
kind = "docs"
summary = "The UnrealI/UnrealShare stale-import-package fact (fixed in mapimport._resolve_actor_class) has no durable dev/docs/unrealed home, only a done/ board item that agents may trim without asking"
+++

# Unreal Gold stale-class-package redirect needs a durable dev/docs/unrealed home

A real UE1 package-format fact — an original (1998/Gold) Unreal `.unr`'s import table can state a
class's home package as `UnrealI` when the shipped System files actually define the class in
`UnrealShare.u` (`Eightball`, `ASMD`, `Barrel`, `TriggerLight`, …), and the real engine must resolve
it somehow since these maps ship and play — is currently documented only in
`dev/docs/board/done/unreal1-ut99-map-import-stale-class-package/overview.md`, cited from
`uedcli/mapimport.py::_resolve_actor_class`.

`dev/docs/unrealed/package-format.md` already exists as the durable home for this kind of fact (it
covers `RF_HasStack`'s per-export placement, `FPoly.ItemName`'s index-0 rule, etc.). This one belongs
there, not in `board/done/`, which agents may trim without asking (`CLAUDE.md`) — a future trim would
leave the code comment's citation dangling and the fact undocumented anywhere durable.

Also worth citing there if confirmed: the exact resolution mechanism is UNVERIFIED — the current fix
assumes a global by-name class lookup (how UE1 registers native classes at boot), inferred only from
the fix working on all 8 corpus maps, no DLL RE. Flagged during review of the fix
(`unreal1-map-class-fallback` worktree, 2026-09-11).

Needs the owner's yes before touching `dev/docs/unrealed/` — propose the exact addition and wait
(`CLAUDE.md` "dev/docs — never edit without the owner's approval").
