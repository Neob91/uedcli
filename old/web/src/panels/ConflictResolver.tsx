// Shared conflict-resolution UI (Task 10) -- ONE component, mounted at TWO call sites with
// different label text and a different onResolve mapping: Save's conflict (a staged actor whose
// trunk Location moved before Save could apply it, uedcli/serve/edits.py `save_staged`) and Load's
// conflict (the same comparison in reverse, `check_load_conflicts`). Both report the same shape
// (`ConflictPayload`: name + staged_location + trunk_location), so one row/picker design serves
// both -- only the two button labels and what the caller does with the picked map differ.
//
// Required, not dismissible (spec): there is no close/cancel affordance. Confirm stays disabled
// until every row has an explicit pick -- declining to pick is not itself a resolution.
import { useState } from 'react'

import type { ConflictPayload } from '../api'

export interface ConflictResolverProps {
  conflicts: ConflictPayload[]
  resolutionLabels: { mine: string; theirs: string }
  // Generic picks, one of 'mine' | 'theirs' per conflicting actor name -- NOT the backend's own
  // resolution vocabulary ('staged'/'trunk' for Save, 'accept-load' for Load). Translating from
  // this generic pick into the real per-direction value is the CALLER's job (SaveBar's own
  // mapToSaveResolutions / App.tsx's mapToAcceptLoadOnly) -- this component knows nothing about
  // either backend route.
  onResolve: (resolutions: Record<string, 'mine' | 'theirs'>) => void
}

function formatLocation(loc: [number, number, number]): string {
  return `${loc.map((v) => v.toFixed(2)).join(', ')}`
}

export function ConflictResolver({ conflicts, resolutionLabels, onResolve }: ConflictResolverProps) {
  const [picks, setPicks] = useState<Record<string, 'mine' | 'theirs'>>({})

  if (conflicts.length === 0) return null

  const allPicked = conflicts.every((c) => picks[c.name] !== undefined)

  const pick = (name: string, choice: 'mine' | 'theirs') => {
    setPicks((p) => ({ ...p, [name]: choice }))
  }

  return (
    <div className="conflict-resolver" role="alertdialog" aria-label="Resolve conflicting edits">
      <p className="conflict-resolver-intro">
        {conflicts.length} actor{conflicts.length === 1 ? '' : 's'} changed elsewhere -- pick a
        resolution for each before continuing.
      </p>
      <ul className="conflict-resolver-rows">
        {conflicts.map((c) => (
          <li key={c.name} className="conflict-resolver-row">
            <div className="conflict-resolver-row-name">{c.name}</div>
            <div className="conflict-resolver-row-locations">
              <span>Your move: {formatLocation(c.staged_location)}</span>
              <span>Trunk value: {formatLocation(c.trunk_location)}</span>
            </div>
            <div className="conflict-resolver-row-choices">
              <label>
                <input
                  type="radio"
                  name={`conflict-resolver-${c.name}`}
                  checked={picks[c.name] === 'mine'}
                  onChange={() => pick(c.name, 'mine')}
                />
                {resolutionLabels.mine}
              </label>
              <label>
                <input
                  type="radio"
                  name={`conflict-resolver-${c.name}`}
                  checked={picks[c.name] === 'theirs'}
                  onChange={() => pick(c.name, 'theirs')}
                />
                {resolutionLabels.theirs}
              </label>
            </div>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="conflict-resolver-confirm"
        disabled={!allPicked}
        onClick={() => onResolve(picks)}
      >
        Apply resolutions
      </button>
    </div>
  )
}
