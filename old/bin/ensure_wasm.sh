#!/bin/bash
# bin/ensure_wasm.sh -- thin CLI wrapper so `web/`'s npm scripts (which can't `source` a bash
# function) have something to shell out to. Mirrors bin/uedcli's own source+call pattern.
set -euo pipefail
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/_venv.sh"
ensure_venv          # `$VENV` (`_venv.sh:21`) is a static path computed at source time, but the
                       # DIRECTORY isn't created until this runs -- both `bin/test:36` and
                       # `bin/uedcli:11` call it before `ensure_native_ext`; `ensure_wasm_artifact`
                       # writes to `$VENV/.uedcli-native-wasm` and needs the same ordering, or a
                       # fresh checkout with no `.venv` yet fails with "No such file or directory".
ensure_wasm_artifact
