// In-GUI level picker (quad-layout Part 7, Task 26, spec §6): a dropdown of every level under the
// project's maps dir; picking a different one calls PUT /api/level, and on success tells the
// parent to adopt the new name. `App.tsx`'s existing `useEffect(..., [level])`s (scene/atlas/
// lightmap fetch, the changes-available WS subscription) already unsubscribe-old/refetch-fresh the
// moment that `level` state changes -- this component's only job is making `level` SETTABLE.
import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'

import type { LevelsPayload } from '../api'
import { fetchLevels, switchLevel } from '../api'

export interface LevelPickerProps {
  currentLevel: string
  // Called AFTER a successful switch -- the caller sets its own `level` state, which drives every
  // existing fetch/subscription effect already keyed on it.
  onLevelChanged: (name: string) => void
}

export function LevelPicker({ currentLevel, onLevelChanged }: LevelPickerProps) {
  const [levels, setLevels] = useState<LevelsPayload['levels']>([])
  const [switching, setSwitching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchLevels()
      .then((payload) => setLevels(payload.levels))
      .catch(() => {
        // A failed levels fetch isn't worth a page-level error -- the picker just stays empty.
      })
  }, [currentLevel])

  const handleChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const name = e.target.value
    if (name === currentLevel) return
    setSwitching(true)
    setError(null)
    switchLevel(name)
      .then(() => onLevelChanged(name))
      .catch((err: unknown) => setError(String(err)))
      .finally(() => setSwitching(false))
  }

  return (
    <div className="level-picker">
      <select
        data-testid="level-picker-select"
        value={currentLevel}
        disabled={switching}
        onChange={handleChange}
      >
        {!levels.some((l) => l.name === currentLevel) && <option value={currentLevel}>{currentLevel}</option>}
        {levels.map((l) => (
          <option key={l.name} value={l.name}>
            {l.name}
          </option>
        ))}
      </select>
      {error && <span className="level-picker-error">{error}</span>}
    </div>
  )
}
