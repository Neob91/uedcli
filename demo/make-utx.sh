#!/usr/bin/env bash
# Regenerate NeonSign.utx from the logo BMP by driving UnrealEd (see make_utx.py).
# Writes /workspace/uedcli/dev/games/deusex/Textures/NeonStrata.utx  (ref: NeonStrata.Neon.Strata).
set -euo pipefail
DEMO_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
ROOT="$(cd "$DEMO_DIR/.." && pwd)"                    # worktree root = uedcli project (game=deusex)
export UEDCLI_HOME="${UEDCLI_HOME:-$DEMO_DIR/.uedcli-home}"

# Reuse the host-native venv bin/uedcli provisions (Pillow + the driver deps).
source "$ROOT/bin/_venv.sh"
ensure_venv
UEDCLI_SKIP_NATIVE=1 exec env PYTHONPATH="$ROOT" "$PY" "$DEMO_DIR/make_utx.py" "$@"
