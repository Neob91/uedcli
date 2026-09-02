+++
priority = "p?"
kind = "implement"
summary = "Cross-tool lint: map actors ↔ dxconcli conversations"
+++

# Cross-tool lint: map actors ↔ dxconcli conversations

A mission's `.con` binds
conversations to actor `BindName`s; nothing verifies the two artifacts agree. A check (either tool's
CLI) that every conversation BindName has a matching actor in the level trunk, and every
conversation-bearing NPC in the map has its `.con` entry — catching silent no-conversation NPCs at
build time instead of in-game. (AI brainstorm 2026-07-16.)
