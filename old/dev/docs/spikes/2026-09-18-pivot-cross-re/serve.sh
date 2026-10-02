#!/bin/bash
# Start this session's OWN backend (port 8795) — never 8765, which is the owner's live preview.
cd /workspace/uedcli/.claude/worktrees/agent-af7a9d5b5d2b653b1
exec /workspace/uedcli/.venv/bin/python -m uedcli --project /workspace/uedcli/_scratch/proj \
  serve --port 8795 wanchai
