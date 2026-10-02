+++
priority = "p3"
kind = "unknown"
summary = "WHERE does `MAP SAVE` create its `Save.tmp`, and can it be left behind or collide?"
+++

# WHERE does `MAP SAVE` create its `Save.tmp`, and can it be left behind or collide?

📖 `core.dll` strings, 2026-07-25 (`unrealed/commands.md` "`MAP SAVE` writes `Save.tmp`") show the
editor serializes into a **fixed-name** `Save.tmp` and then moves it onto the target — but the
string is a bare filename, so its DIRECTORY (beside the destination? the editor's cwd?) is inferred,
not extracted, and everything below depends on it. Cheap to settle live: drive a `MAP SAVE` of a big
map and `ls`/`inotifywait` the container's `/work` and `/opt/UED22` while it runs. If the temp does
land beside the destination: `xfer.remove` only reclaims the uuid-named work file, so a wedge
mid-save leaves a stray `Save.tmp` for the container's life (harmless while the container is
ephemeral, but it is state nobody owns), and — more importantly — two saves into one directory in
one container would fight over the single temp. Nothing does that today (one save per invocation),
but the warm-editor path makes it thinkable. The same probe would also settle whether the move is a
rename or a copy (watch the destination's size/inode), which is the open question behind
`map_save`'s structural check — and, in the same trace, whether the destination is ever opened
WITHOUT truncation. That last one is a real hole in the check: a size-preserving in-place rewrite
would hold `size` constant for the whole write, so the stability signal is satisfied throughout and
the header check compares the NEW header against the OLD, larger size — i.e. a mid-write file could
be accepted. Unreachable for both production callers (fresh uuid paths, nothing pre-exists) but
live for any fixed-path caller. (2026-07-25, cold reviews of the `map_save` change; evidence so far
in `spikes/2026-07-25-map-save-mechanism/`.)
