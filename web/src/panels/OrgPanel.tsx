// Organization panel (quad-layout Part 6, Task 23): folder tree + label facets + a find box
// mirroring `actor find`. Folder-node selection is a REAL multi-actor selection (spec §5, reconciled
// with Part 3's selectedNames model) -- a plain click REPLACES the selection with the folder's full
// actor set (mirrors a viewport tap's replace semantics), Ctrl-click ADDS it (mirrors Ctrl+tap's
// additive semantics). `onSelectActor` here is intentionally a DIFFERENT shape than Viewport3D's/
// OrthoViewport's own `onSelectActor(name, additive)` -- this component always selects a BATCH.
import { useEffect, useMemo, useRef, useState } from 'react'

import type { SceneActor } from '../api'
import type { FolderNode } from '../scene/orgFilter'
import { buildFolderTree, matchesFind, matchesLabelFacets } from '../scene/orgFilter'

export interface OrgPanelProps {
  actors: SceneActor[]
  selectedNames: ReadonlySet<string>
  onSelectActor: (names: string[], additive: boolean) => void
}

function isTypingTarget(t: EventTarget | null): boolean {
  return t instanceof HTMLElement && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
}

function collectNames(node: FolderNode): string[] {
  const names = node.actors.map((a) => a.name)
  for (const child of node.children) names.push(...collectNames(child))
  return names
}

function leafLabel(path: string): string {
  const segments = path.split('.')
  return segments[segments.length - 1]
}

function FolderTreeNode({
  node,
  onSelect,
}: {
  node: FolderNode
  onSelect: (names: string[], additive: boolean) => void
}) {
  const path = node.path as string // never called for the root/(no folder) bucket
  const names = useMemo(() => collectNames(node), [node])
  return (
    <li>
      <button
        type="button"
        data-testid={`org-folder-${path}`}
        onClick={(e) => onSelect(names, e.ctrlKey || e.metaKey)}
      >
        {leafLabel(path)} ({names.length})
      </button>
      {node.children.length > 0 && (
        <ul>
          {node.children.map((child) => (
            <FolderTreeNode key={child.path} node={child} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  )
}

export function OrgPanel({ actors, selectedNames, onSelectActor }: OrgPanelProps) {
  const [activeLabels, setActiveLabels] = useState<Set<string>>(new Set())
  const [findText, setFindText] = useState('')
  const findRef = useRef<HTMLInputElement | null>(null)

  // `/`/`Ctrl+F` focus-search (main spec's "Keybindings", folded in here per the org panel's own
  // find box): `/` types normally once a DIFFERENT text input already has focus (never steals it,
  // and never calls preventDefault -- only Ctrl+F needs that, to stop the browser's own
  // find-in-page). Same isTypingTarget guard pattern as SelectionKeys/FlyKeys.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isTypingTarget(e.target)) return
      const isCtrlF = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f'
      if (e.key !== '/' && !isCtrlF) return
      if (isCtrlF) e.preventDefault()
      findRef.current?.focus()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const tree = useMemo(() => buildFolderTree(actors), [actors])
  const allLabels = useMemo(() => {
    const set = new Set<string>()
    for (const actor of actors) for (const label of actor.labels) set.add(label)
    return [...set].sort()
  }, [actors])

  // Find-box matching: name/class glob via matchesFind, wrapped as a substring search (`*text*`) --
  // full flag-shaped query syntax (`class:X folder:Y`) is a reasonable follow-up, not built here.
  const findResults = useMemo(() => {
    const text = findText.trim()
    if (text === '') return null
    return actors.filter(
      (actor) => matchesLabelFacets(actor, activeLabels) && matchesFind(actor, { name: `*${text}*` }),
    )
  }, [actors, activeLabels, findText])

  const toggleLabel = (label: string) => {
    setActiveLabels((s) => {
      const next = new Set(s)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  const noFolderNames = tree.actors.map((a) => a.name)

  return (
    <div className="org-panel" data-testid="org-panel">
      <input
        ref={findRef}
        data-testid="org-find"
        type="text"
        placeholder="find (name glob)…"
        value={findText}
        onChange={(e) => setFindText(e.target.value)}
      />
      {allLabels.length > 0 && (
        <div className="org-labels">
          {allLabels.map((label) => (
            <button
              key={label}
              type="button"
              className={activeLabels.has(label) ? 'org-label-chip active' : 'org-label-chip'}
              onClick={() => toggleLabel(label)}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      {findResults ? (
        <ul className="org-results" data-testid="org-results">
          {findResults.map((a) => (
            <li key={a.name} className={selectedNames.has(a.name) ? 'selected' : ''}>
              <button type="button" onClick={(e) => onSelectActor([a.name], e.ctrlKey || e.metaKey)}>
                {a.name}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="org-tree">
          <li>
            <button
              type="button"
              data-testid="org-folder-no-folder"
              onClick={(e) => onSelectActor(noFolderNames, e.ctrlKey || e.metaKey)}
            >
              (no folder) ({noFolderNames.length})
            </button>
          </li>
          {tree.children.map((child) => (
            <FolderTreeNode key={child.path} node={child} onSelect={onSelectActor} />
          ))}
        </ul>
      )}
    </div>
  )
}
