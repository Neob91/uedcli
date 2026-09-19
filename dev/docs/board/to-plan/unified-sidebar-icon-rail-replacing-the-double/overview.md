+++
priority = "p2"
kind = "implement"
summary = "Replace OrgPanel + Inspector's two independent sidebars with one icon-rail sidebar; launch panels are Selection and Org/Search"
+++

# Unified sidebar: icon rail replacing the double sidebar

Owner-reviewed design, worked out interactively (chat + an artifact mockup,
<https://claude.ai/code/artifact/485cc13d-166f-47f9-8846-a079e656ba43>). Full detail in `spec.md`.
Ready for `plan.md`.

Today's org panel (`OrgPanel.tsx`) and inspector pane (`Inspector.tsx`) are two independently
collapsible sidebars, both right-aligned but mounted at two different DOM levels (org panel nested
inside `QuadLayout.tsx`, inspector a top-level sibling in `App.tsx`) — the root cause of at least one
past layout bug (toolbar-overlap, see `QuadLayout.tsx`'s comment history). This replaces both with one
`Sidebar` component: a permanent icon rail plus one active panel, extensible to future panels
(texture search/align, sound/music search, editable properties) by adding registry entries only.
