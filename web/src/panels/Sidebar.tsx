// The unified sidebar (icon rail + one active panel), replacing the old org-panel/inspector-pane
// double sidebar (unified-sidebar spec). Purely presentational: collapse/active-tab state and each
// panel's `hasIndicator` are all owned by the caller (App.tsx, via useSidebar/useSelectionSeen) and
// passed in as props -- Sidebar knows nothing about what a panel contains, or why any panel's
// indicator is on, so a future panel's own indicator condition needs no change here.
import type { SceneActor } from '../api'
import type { SurfaceSelection } from './Inspector'
import type { SidebarPanelDef } from './sidebarRegistry'

export interface SidebarProps {
  panels: SidebarPanelDef[]
  collapsed: boolean
  activeTabId: string
  setActiveTab: (id: string) => void
  selectedActors: SceneActor[]
  selectedSurfaces: SurfaceSelection[]
}

function actorLineText(actors: SceneActor[]): string {
  return actors.length === 1 ? `${actors[0].name} · ${actors[0].cls}` : `${actors.length} actors`
}

function surfaceLineText(surfaces: SurfaceSelection[]): string {
  if (surfaces.length === 1) {
    const { actorName, polyIndex, poly } = surfaces[0]
    const texture = poly.tex_index >= 0 ? `#${poly.tex_index}` : '(untextured)'
    return `${actorName}:${polyIndex} · ${texture}`
  }
  return `${surfaces.length} surfaces`
}

/** The persistent "current selection" strip (spec's Decisions section): always mounted above
 * `.sidebar-body`, independent of which tab is showing AND independent of collapse state (spec:
 * "the strip stays visible even when the sidebar is collapsed, shrunk to its icon token(s) only").
 * When `collapsed`, each non-empty kind's line drops its text entirely -- just the icon token,
 * since there's no room for it in the ~36px rail width once `.sidebar-panel` is gone. */
function SelectionStrip({
  actors,
  surfaces,
  collapsed,
  onClick,
}: {
  actors: SceneActor[]
  surfaces: SurfaceSelection[]
  collapsed: boolean
  onClick: () => void
}) {
  const empty = actors.length === 0 && surfaces.length === 0
  return (
    <div
      className={collapsed ? 'selection-strip selection-strip-collapsed' : 'selection-strip'}
      data-testid="selection-strip"
      onClick={onClick}
    >
      {empty ? (
        !collapsed && (
          <div className="selection-strip-line selection-strip-empty" data-testid="selection-strip-empty">
            No selection
          </div>
        )
      ) : (
        <>
          {actors.length > 0 && (
            <div className="selection-strip-line" data-testid="selection-strip-actor">
              <span className="selection-strip-icon" aria-hidden="true">
                ▣
              </span>
              {!collapsed && actorLineText(actors)}
            </div>
          )}
          {surfaces.length > 0 && (
            <div className="selection-strip-line" data-testid="selection-strip-surface">
              <span className="selection-strip-icon" aria-hidden="true">
                ▦
              </span>
              {!collapsed && surfaceLineText(surfaces)}
            </div>
          )}
        </>
      )}
    </div>
  )
}

export function Sidebar({ panels, collapsed, activeTabId, setActiveTab, selectedActors, selectedSurfaces }: SidebarProps) {
  const activePanel = panels.find((p) => p.id === activeTabId)

  // The strip's own click never collapses -- it always means "go to Selection", never "toggle
  // collapse". Reusing setActiveTab RAW here would collapse the sidebar if the user clicks the
  // strip while already on the (expanded) Selection tab, which is not what a control whose whole
  // point is staying visible at all times should do on a click.
  const onStripClick = () => {
    if (collapsed || activeTabId !== 'selection') setActiveTab('selection')
  }

  return (
    <div className="sidebar" data-testid="sidebar">
      <SelectionStrip actors={selectedActors} surfaces={selectedSurfaces} collapsed={collapsed} onClick={onStripClick} />
      <div className="sidebar-body">
        <div className="sidebar-rail">
          {panels.map((panel) => (
            <button
              key={panel.id}
              type="button"
              className="sidebar-rail-button"
              data-testid={`sidebar-rail-${panel.id}`}
              aria-pressed={!collapsed && panel.id === activeTabId}
              title={panel.title}
              onClick={() => setActiveTab(panel.id)}
            >
              {panel.icon}
              {panel.hasIndicator && (
                <span className="sidebar-rail-dot" data-testid={`sidebar-dot-${panel.id}`} aria-hidden="true" />
              )}
            </button>
          ))}
        </div>
        {!collapsed && activePanel && (
          <div className="sidebar-panel">
            <div className="sidebar-panel-body">{activePanel.content}</div>
          </div>
        )}
      </div>
    </div>
  )
}
