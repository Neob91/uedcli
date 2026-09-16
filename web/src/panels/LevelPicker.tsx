// In-GUI level picker (quad-layout Part 7, Task 26, spec §6): a dropdown of every level under the
// project's maps dir. A level switch invalidates far more of App's own state (scene/atlas/
// lightmap/status/selection) than this component owns, so the PUT /api/level call and the
// unload-then-block flow live in App.tsx -- this component stays a dumb dropdown that reports
// which level was picked, plus the switch-failure message App hands back.
import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'

import type { LevelsPayload } from '../api'
import { fetchLevels } from '../api'

export interface LevelPickerProps {
  currentLevel: string
  // True while a switch is in flight -- App unmounts the whole app during this window anyway, but
  // this keeps the select itself honest if that ever changes.
  disabled: boolean
  // The last switch-attempt failure, if any (App owns and clears it).
  error: string | null
  onSwitchLevel: (name: string) => void
}

export function LevelPicker({ currentLevel, disabled, error, onSwitchLevel }: LevelPickerProps) {
  const [levels, setLevels] = useState<LevelsPayload['levels']>([])

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
    onSwitchLevel(name)
  }

  return (
    <div className="level-picker">
      <select
        data-testid="level-picker-select"
        value={currentLevel}
        disabled={disabled}
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
