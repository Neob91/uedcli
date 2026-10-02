# Runs the geometry-alignment eval's subject `claude -p` process, isolated from
# THIS host's own /etc/claude-code/CLAUDE.md (a sandbox-specific org policy file
# injected at that fixed system path -- see EVAL-PROCEDURE.md). Isolated HOME
# alone doesn't hide it (it's not under HOME); a plain container built from this
# image never has it, since it's a path this box's own launcher injects into ITS
# containers, not something baked into any public base image (confirmed by
# testing a bare `alpine` container, per the commit that added this file).
#
# uedcli's own PYTHON source is NOT baked in here -- it's installed fresh from a
# bind-mounted source tree at container start (entrypoint.sh), so a container
# never runs a stale copy of whatever the checkout currently has. Its only
# third-party runtime dependency (Pillow) IS baked in, since that changes far
# less often -- as is the compiled uedcli_native wheel (run_eval.py's
# _ensure_docker_image copies it in transiently; never committed, see
# .gitignore): `actor add`/`brush build`/`actor duplicate` need it to parse a
# real .u package's class schema, and a native build is far too slow to redo
# on every container start.
FROM python:3.12-bookworm

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# Pinned, not floating, for reproducibility -- an unpinned `npm install -g
# @anthropic-ai/claude-code` would silently drift to whatever's current on
# each image rebuild. NOT what fixes the Bash-tool permission stall this
# project hit under Docker (see run_eval.py's `_run_claude` docstring for
# that: it's `--dangerously-skip-permissions` -- confirmed by testing that
# EVERY claude-code version tried, this pin included, stalls the same way
# inside a container without it). Bump this version deliberately, re-verify
# the container still behaves as expected, never let it drift unnoticed.
RUN npm install -g @anthropic-ai/claude-code@2.1.261 \
 && pip install --no-cache-dir 'Pillow>=11'

COPY uedcli_native-*.whl /tmp/
RUN pip install --no-cache-dir /tmp/uedcli_native-*.whl && rm /tmp/uedcli_native-*.whl

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
