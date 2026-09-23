// Session picker (persistent-GUI-editing-sessions plan, Task 16) -- replaces LevelPicker's PUT
// /api/level level switch. Lists every open session (across every level, grouped), and reports
// which one was picked; App.tsx (via SessionContext's own `reload`) decides what happens next --
// this stays a dumb dropdown, same division of labor LevelPicker.tsx used to have.
import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'

import type { SessionSummary } from '../api'
import { fetchSessions } from '../api'

export interface SessionDropdownProps {
  currentSessionId: string | null
  // Called with the picked session's id when it differs from `currentSessionId`. App.tsx writes
  // the id into the URL and re-resolves the session (SessionContext's `reload`) -- the ONE
  // navigation mechanism a session switch uses, whether triggered here or by a fresh page load.
  onSwitchSession: (sessionId: string) => void
}

function groupByLevel(sessions: readonly SessionSummary[]): Map<string, SessionSummary[]> {
  const groups = new Map<string, SessionSummary[]>()
  for (const session of sessions) {
    const group = groups.get(session.level)
    if (group) group.push(session)
    else groups.set(session.level, [session])
  }
  return groups
}

export function SessionDropdown({ currentSessionId, onSwitchSession }: SessionDropdownProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])

  useEffect(() => {
    fetchSessions()
      .then((payload) => setSessions(payload.sessions))
      .catch(() => {
        // A failed sessions fetch isn't worth a page-level error -- the dropdown just stays empty.
      })
  }, [currentSessionId])

  const handleChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    if (id === currentSessionId) return
    onSwitchSession(id)
  }

  const groups = groupByLevel(sessions)
  const knownCurrent = sessions.some((s) => s.id === currentSessionId)

  return (
    <div className="session-dropdown">
      <select data-testid="session-dropdown-select" value={currentSessionId ?? ''} onChange={handleChange}>
        {currentSessionId && !knownCurrent && <option value={currentSessionId}>{currentSessionId}</option>}
        {[...groups.entries()].map(([level, group]) => (
          <optgroup key={level} label={level}>
            {group.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  )
}
