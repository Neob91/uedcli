# MVP — most important issues

The owner's priority focus: the board items that matter most, linked by slug. This is a curated,
cross-cutting view, **not** a board stage — each item keeps its own stage and lifecycle on the board;
this only tracks which ones are the priority. Drop an entry once it lands.

- board item `incremental-gui-reload-only-re-resolve-actors` — GUI Reload re-resolves every actor
  from scratch on every call; want it to diff against the session's last-loaded snapshot and only
  re-resolve actors that changed, targeting hundreds of ms instead of scaling with the whole level.
