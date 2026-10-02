// Shared click-to-edit-in-place control (session-management-UI spec, decision 4): a ✓/✗ button
// pair plus Enter/Esc confirms or cancels. Used by both SessionPicker's rows and SessionLabel.
import { useState } from 'react'
import type { KeyboardEvent } from 'react'

export interface InlineRenameProps {
  // The current name, or null when unnamed -- `placeholder` is shown instead in that case.
  value: string | null
  placeholder: string
  onRename: (name: string) => void
  // Optional tooltip for the display span (e.g. SessionLabel shows the raw session id on hover).
  title?: string
}

export function InlineRename({ value, placeholder, onRename, title }: InlineRenameProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  const startEditing = () => {
    setDraft(value ?? '')
    setEditing(true)
  }

  const confirm = () => {
    onRename(draft)
    setEditing(false)
  }

  const cancel = () => {
    setEditing(false)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') confirm()
    else if (e.key === 'Escape') cancel()
  }

  if (!editing) {
    return (
      <span className="inline-rename-display" title={title} onClick={startEditing}>
        {value ?? placeholder}
      </span>
    )
  }

  return (
    <span className="inline-rename-editing">
      <input
        type="text"
        value={draft}
        autoFocus
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
      />
      <button type="button" aria-label="confirm rename" onClick={confirm}>
        ✓
      </button>
      <button type="button" aria-label="cancel rename" onClick={cancel}>
        ✗
      </button>
    </span>
  )
}
