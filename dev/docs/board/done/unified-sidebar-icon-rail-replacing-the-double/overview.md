+++
priority = "p2"
kind = "implement"
summary = "Replace OrgPanel + Inspector's two independent sidebars with one icon-rail sidebar; launch panels are Selection and Org/Search"
+++

# Unified sidebar: icon rail replacing the double sidebar

DONE (2026-09-20). One `Sidebar` component (icon rail + one active panel + a persistent
actor/surface selection strip, visible even when collapsed) replaces the old independent
`OrgPanel`/`Inspector` sidebars. New: `sidebarRegistry.ts`, `useSidebar.ts`, `useSelectionSeen.ts`,
`Sidebar.tsx` (+ tests). Spec/plan went through two review-and-fix rounds each; build reviewed
independently, 511/511 tests green, `tsc -b` clean. `dev/docs/GUI.md` update flagged as a follow-up
needing the owner's yes, not done here.
