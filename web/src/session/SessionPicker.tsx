// The landing screen (session-management-UI spec, decision 1): replaces auto-create-on-bare-URL
// entirely -- a bare "/" always shows this, and nothing is created without an explicit click here.
import { useEffect, useState } from 'react'

import type { SessionSummary } from '../api'
import { createSession, deleteSession, fetchLevels, fetchSession, fetchSessions, fetchStaged, renameSession, setClaimToken } from '../api'
import { InlineRename } from './InlineRename'
import { navigate } from './route'

function sortByLastActiveDescending(sessions: readonly SessionSummary[]): SessionSummary[] {
  return [...sessions].sort((a, b) => b.last_active_at.localeCompare(a.last_active_at))
}

export function SessionPicker() {
  const [levels, setLevels] = useState<string[]>([])
  const [selectedLevel, setSelectedLevel] = useState('')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [creating, setCreating] = useState(false)
  // One error state for all six catch sites below (fetchLevels, fetchSessions, handleCreate,
  // handleRename, handleDelete, the fetchStaged pre-check inside handleDelete) -- whichever fires
  // last wins, no queue. Mirrors App.tsx's `buildError` banner pattern. A real failure (a 409 claim
  // race, a network error) used to only console.error, with nothing visible on screen.
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchLevels()
      .then((payload) => {
        setLevels(payload.levels.map((l) => l.name))
        setSelectedLevel(payload.current || payload.levels[0]?.name || '')
      })
      .catch((e: unknown) => {
        console.error('fetchLevels failed', e)
        setError(String(e))
      })
    fetchSessions()
      .then((payload) => setSessions(payload.sessions))
      .catch((e: unknown) => {
        console.error('fetchSessions failed', e)
        setError(String(e))
      })
  }, [])

  const handleCreate = () => {
    if (!selectedLevel) return
    setCreating(true)
    createSession(selectedLevel)
      .then((rec) => navigate(`/session/${rec.id}/`))
      .catch((e: unknown) => {
        console.error('createSession failed', e)
        setError(String(e))
      })
      .finally(() => setCreating(false))
  }

  const handleRowClick = (id: string) => {
    navigate(`/session/${id}/`)
  }

  // Both rename and delete from here need a claim token this tab has never held for most rows --
  // acquiring one first (GET, which mints a fresh one) is the deliberate, spec'd side effect: it
  // supersedes whatever window currently holds this session's claim, same as any other claim mint.
  // Applying it via setClaimToken is the load-bearing part -- renameSession/deleteSession read the
  // token from api.ts's own module-level current-claim variable (withClaimToken), never from a
  // value passed in here, so fetching the token alone does nothing without also setting it.
  const acquireClaim = (id: string): Promise<void> =>
    fetchSession(id).then((rec) => {
      setClaimToken(rec.claim_token)
    })

  const handleRename = (id: string, name: string) => {
    acquireClaim(id)
      .then(() => renameSession(id, name))
      .then((result) => {
        setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, name: result.name } : s)))
      })
      .catch((e: unknown) => {
        console.error('rename failed', e)
        setError(String(e))
      })
  }

  const handleDelete = (id: string) => {
    fetchStaged(id)
      .then((staged) => {
        const hasUnsaved = Object.keys(staged).length > 0
        const message = hasUnsaved
          ? 'This session has unsaved edits. Delete anyway?'
          : 'Delete this session?'
        if (!window.confirm(message)) return
        acquireClaim(id)
          .then(() => deleteSession(id, { force: hasUnsaved }))
          .then(() => setSessions((prev) => prev.filter((s) => s.id !== id)))
          .catch((e: unknown) => {
            console.error('delete failed', e)
            setError(String(e))
          })
      })
      .catch((e: unknown) => {
        console.error('fetching staged state failed', e)
        setError(String(e))
      })
  }

  return (
    <div className="session-picker">
      {error && (
        <div className="session-error-banner">
          {error}
          <button type="button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}
      <div className="session-picker-create">
        <select value={selectedLevel} onChange={(e) => setSelectedLevel(e.target.value)}>
          {levels.map((level) => (
            <option key={level} value={level}>
              {level}
            </option>
          ))}
        </select>
        <button type="button" onClick={handleCreate} disabled={creating || !selectedLevel}>
          Create session
        </button>
      </div>
      <div className="session-picker-list">
        {sortByLastActiveDescending(sessions).map((s) => (
          <div key={s.id} data-testid="session-picker-row" className="session-picker-row" onClick={() => handleRowClick(s.id)}>
            <span title={s.id} onClick={(e) => e.stopPropagation()}>
              <InlineRename value={s.name} placeholder={s.level} onRename={(name) => handleRename(s.id, name)} />
            </span>
            {s.name && <span className="session-picker-row-level">{s.level}</span>}
            <span className="session-picker-row-active">{s.last_active_at}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                handleDelete(s.id)
              }}
            >
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
