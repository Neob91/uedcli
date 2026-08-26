#!/usr/bin/env bash
# Reproduce the editor-free build end to end. Run from the repo root with a project whose
# `maps/<level>/` holds the trunk (`level import` a shipped `.dx` to make one).
#
#     dev/docs/spikes/2026-08-26-editor-free-native-materialize/harness/build-and-preview.sh \
#         <project-dir> <level-name> <out-dir>
#
# `UEDCLI_NATIVE_MATERIALIZE=1` is the temporary gate that routes `level materialize` to the
# editor-free native build: no editor container, no MAP LOAD/REBUILD, no LIGHT APPLY. `level preview
# --game` then drives the GAME client (`DeusEx.exe`), a different binary from the editor, to confirm
# the map loads and renders.
set -euo pipefail
proj="$1"; level="$2"; out="$3"
dx="$out/$level.dx"
mkdir -p "$out"

UEDCLI_NATIVE_MATERIALIZE=1 bin/uedcli --project "$proj" level materialize \
  --tree "level/$level" --out "$dx" --overwrite

# `@Name` resolves against the map being previewed; swap these for actors the level actually has.
bin/uedcli --project "$proj" level preview --game --map "$dx" --out-dir "$out" \
  'at:@PathNode0;rot:0,0;name:pathnode0' \
  'at:@PathNode213;rot:0,0;name:pathnode213'
