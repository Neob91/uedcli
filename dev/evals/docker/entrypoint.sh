#!/bin/sh
# Installs uedcli fresh from the bind-mounted source (/uedcli-src/uedcli and
# /uedcli-src/pyproject.toml, each mounted read-only) on every container
# start -- cheap (pure Python, deps already baked into the image), and
# guarantees the container never runs a stale copy of the checkout.
#
# The container runs as a NON-root user (run_eval.py passes `--user
# <host-uid>:<host-gid>`) for least privilege -- this is NOT what fixes the
# Bash-tool permission stall (see run_eval.py's `_run_claude` docstring for
# that: it's `--dangerously-skip-permissions`, needed regardless of UID,
# since container-vs-bare-host is the variable that actually matters).
# As non-root, /uedcli-src (an auto-created, root-owned mount point, only
# its two children are actual mounts) is very likely not writable, so `pip
# install -e` there would fail the same way a wholly read-only mount does.
# Copy to /tmp first (world-writable, sticky bit) and install with --user,
# which targets $HOME/.local instead of the system site-packages a non-root
# user can't write to either.
set -e
cp -r /uedcli-src /tmp/uedcli-src
pip install --no-cache-dir --no-deps --user -e /tmp/uedcli-src -q
export PATH="$HOME/.local/bin:$PATH"

# The real Deus Ex asset tree, bind-mounted read-only at /dx-assets (run_eval.py) -- without a
# config pointing at it, `actor add`/`brush build`/`actor duplicate` (anything needing a class
# schema from a real .u package) fail outright. Same [games.deusex] shape as this host's own
# ~/.uedcli/config.toml, just re-rooted at the container's mount point.
if [ -d /dx-assets ]; then
  mkdir -p "$HOME/.uedcli"
  cat > "$HOME/.uedcli/config.toml" <<EOF
[games.deusex]
paths = "/dx-assets/System:/dx-assets/Textures:/dx-assets/Sounds:/dx-assets/Music:/dx-assets/Maps"
EOF
fi

exec "$@"
