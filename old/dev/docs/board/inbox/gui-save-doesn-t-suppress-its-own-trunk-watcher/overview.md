+++
priority = "p?"
kind = "debug"
summary = "GUI: Save doesn't suppress its own trunk-watcher changes-available banner"
depends-on = ["gui-p2-actor-translate-ctrl-drag"]
+++

# GUI: Save doesn't suppress its own trunk-watcher changes-available banner

Found in the final whole-branch review of `gui-p2-actor-translate-ctrl-drag` (P2 slice 1: actor
move + Save/Discard/Load conflicts), confirmed again in the fix-wave re-review — not a regression
from that work, a residual gap it correctly declined to fix outside its authorized scope.

## What happens

A successful GUI Save now correctly refreshes the client (routes through the same `runBuildAction`
path Load/Rebuild use — `web/src/App.tsx`'s `onSaved`). But the GUI's own trunk write still trips
its own `TrunkWatcher` (`uedcli/serve/watch.py`, 0.4s debounce), which sets `_changes_available[0]
= True` independently of the client-driven refresh. Whichever finishes second wins:

- If the client's own post-Save `/load` round-trip completes in under ~0.4s (true for small/medium
  levels — **this is the default case, not a rare race**), the watcher's callback fires AFTER
  `/load` already cleared the flag, re-setting it — so the user sees "changes available, reload?"
  for their own successful save, as if someone else had edited the trunk.
- Only when `/load` itself takes longer than ~0.4s does the ordering invert and the banner stay
  suppressed.

`web/src/App.tsx`'s current comment on this ("*if* that debounced callback fires AFTER…") understates
it — reword when fixing, it reads as an edge case but isn't one.

## Why not fixed in the original change

Needs a backend change outside a frontend-only fix wave's scope: either `/save` should clear
`_changes_available[0]` the same way `/load` does (`uedcli/serve/app.py`), or the watcher should
recognize/suppress a change it triggered itself.

## Fix shape (not decided, just sketched)

- Simplest: have the `/save` route clear `_changes_available[0] = False` itself, same as `/load`
  already does (`app.py`'s `load()` handler, `_changes_available[0] = False`) — since the client is
  about to `/load` anyway right after a successful Save, this pre-empts the watcher's own (correct,
  but redundant) detection of the same write.
- Alternative: have the watcher ignore a write it can attribute to the GUI's own just-completed
  Save (e.g. a short suppression window keyed by the Save response), if clearing eagerly in `/save`
  turns out to have some other downside not obvious here.

## Refs

- Board item this was found reviewing: `gui-p2-actor-translate-ctrl-drag`.
- `uedcli/serve/watch.py` (`TrunkWatcher`, 0.4s debounce), `uedcli/serve/app.py` (`load()`'s
  `_changes_available[0] = False`, the `/save` route), `web/src/App.tsx` (`onSaved`, the
  under-stated comment).
