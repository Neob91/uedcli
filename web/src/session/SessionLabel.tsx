// The toolbar's persistent session identity label (session-management-UI spec, decisions 4/5/6):
// always shows the current session's name-or-level, is itself the rename trigger, and carries a
// back-to-picker link. Renaming here uses the session's OWN already-held claim token (via
// renameSession -> api.ts's withClaimToken -> the module-level token App.tsx already pushed in) --
// never a fresh acquire-then-mutate GET, which SessionPicker's rows need instead (they hold no
// token at all for a session this tab never opened) but this component must not, or it would
// supersede its own window's claim.
import { useState } from 'react'

import { renameSession } from '../api'
import { InlineRename } from './InlineRename'
import { navigate } from './route'

export interface SessionLabelProps {
  sessionId: string
  level: string
  name: string | null
  onRenamed: (name: string | null) => void
}

export function SessionLabel({ sessionId, level, name, onRenamed }: SessionLabelProps) {
  // A failed rename used to only console.error, with nothing shown on screen -- a real 409 (a
  // claim race) produced no visible change at all. Mirrors App.tsx's `buildError` banner pattern.
  const [error, setError] = useState<string | null>(null)

  const handleRename = (draft: string) => {
    renameSession(sessionId, draft)
      .then((result) => onRenamed(result.name))
      .catch((e: unknown) => {
        console.error('rename failed', e)
        setError(String(e))
      })
  }

  return (
    <div className="session-label">
      {error && (
        <div className="session-error-banner">
          {error}
          <button type="button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}
      <InlineRename value={name} placeholder={level} title={sessionId} onRename={handleRename} />
      <button type="button" aria-label="back to sessions" onClick={() => navigate('/')}>
        ⌂ Sessions
      </button>
    </div>
  )
}
