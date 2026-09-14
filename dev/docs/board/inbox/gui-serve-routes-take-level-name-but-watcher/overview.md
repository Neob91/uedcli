+++
priority = "p3"
kind = "implement"
summary = "GUI serve routes take {level_name} but the watcher binds one level; reconcile in Slice 2."
depends-on = ["uedcli-human-gui"]
+++

# GUI serve routes take level_name but watcher binds one level

Found reviewing Slice 1 of `uedcli-human-gui`. The `serve` process is launched against one level and
`TrunkWatcher`/the WS reload are bound to that level, but `GET /api/level/{level_name}/scene` and
`/atlas` take an independent path param and will solve **any** level under the project maps dir. So a
client requesting a different level gets a scene that never live-reloads — a gap between the
"one level per process" Slice-1 design and the routing.

Harmless in Slice 1 (read-only; ordinary read access only), so the owner ruled to **defer to Slice 2**
(2026-09-13): Slice 2 adds the in-GUI level picker and genuinely wants level-parameterized routes, so
reconcile it then — either the picker re-launches/retargets the watcher per selected level, or the
routes are bound to the app's captured level with the picker driving process/target switching.

Also confirm path-param safety when this is picked up (reject `../`/absolute in `{level_name}`), if
the Slice-1 build didn't already.
