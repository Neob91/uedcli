// Save/Discard bar for staged actor moves (Task 10) -- the missing UI piece over Tasks 1-4's
// staging backend and Tasks 5-9's drag-to-stage mechanics. Renders nothing until something is
// staged; a Save conflict (uedcli/serve/edits.py `save_staged`'s per-actor Location check) mounts
// the shared `ConflictResolver` and blocks Save until every conflicting row is resolved.
//
// `stagedNames` is a display-only signal, not authoritative staging state (App.tsx owns it, kept
// deliberately approximate -- see App.tsx's own doc comment): the actual conflict set this
// component drives comes straight from each `postSave` response, not from `stagedNames`. Save is
// inherently whole-level (`save_staged` applies every currently-staged actor for the level in one
// call, not a caller-chosen subset), so once a `postSave` call returns NO conflicts, the level's
// entire stage is empty and it's correct to tell App to clear `stagedNames` outright (`onSaved()`).
// The same holds for `onDiscarded()`: it fires on the whole-level Discard button, and on resolving
// the LAST remaining conflict via the per-actor discard escape hatch below -- at that point every
// staged actor for the level really is gone (the first `postSave` call already auto-applied and
// cleared every NON-conflicting actor in the same round-trip that surfaced these conflicts, so the
// conflicting set IS the level's entire remaining stage while any conflict is pending).
import { useCallback, useEffect, useState } from 'react'

import type { ConflictPayload } from '../api'
import { postDiscard, postSave } from '../api'
import { ConflictResolver } from './ConflictResolver'

export interface SaveBarProps {
  level: string
  stagedNames: ReadonlySet<string>
  // Called once a Save round-trip completes with NO remaining conflicts (the level's whole stage
  // is now empty) -- App.tsx clears its own `stagedNames`.
  onSaved: () => void
  // Called once the level's whole stage is confirmed empty via a discard path: the top-level
  // Discard button, or the per-actor conflict-discard escape hatch clearing the LAST conflict.
  onDiscarded: () => void
  // Fires for the per-actor conflict-discard escape hatch specifically (NOT the whole-level
  // Discard button, which only ever needs `onDiscarded`) -- lets App.tsx drop that ONE actor's
  // client-rendered staged position too (Critical 2, final review fix wave), so a later Load
  // doesn't keep showing a stale offset for an actor whose own stage was just dropped. Optional:
  // a caller that doesn't track staged positions client-side can omit it.
  onActorDiscarded?: (name: string) => void
}

/** Save's own resolutionLabels/mapping -- 'mine' keeps the staged move, 'theirs' keeps the current
 * trunk value (a no-op write that still clears the stage, `save_staged`'s own "trunk" branch). */
const SAVE_RESOLUTION_LABELS = { mine: 'Keep my move', theirs: 'Keep trunk value' }

function mapToSaveResolutions(picks: Record<string, 'mine' | 'theirs'>): Record<string, 'staged' | 'trunk'> {
  const out: Record<string, 'staged' | 'trunk'> = {}
  for (const [name, pick] of Object.entries(picks)) {
    out[name] = pick === 'theirs' ? 'trunk' : 'staged'
  }
  return out
}

export function SaveBar({ level, stagedNames, onSaved, onDiscarded, onActorDiscarded }: SaveBarProps) {
  const [conflicts, setConflicts] = useState<ConflictPayload[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A level switch invalidates this component's own local conflict/busy/error state -- a stale
  // conflict row (or an in-flight request) from the PREVIOUS level must never linger and get
  // posted against the new one. Mirrors App.tsx's own `handleSwitchLevel` resetting its sibling
  // `loadConflicts` state on the same signal (review finding).
  useEffect(() => {
    setConflicts([])
    setBusy(false)
    setError(null)
  }, [level])

  const runSave = useCallback(
    (resolutions: Record<string, 'staged' | 'trunk'>) => {
      setBusy(true)
      setError(null)
      postSave(level, resolutions)
        .then((result) => {
          setConflicts(result.conflicts)
          if (result.conflicts.length === 0) onSaved()
        })
        .catch((e: unknown) => setError(String(e)))
        .finally(() => setBusy(false))
    },
    [level, onSaved],
  )

  const handleSave = useCallback(() => runSave({}), [runSave])

  const handleDiscard = useCallback(() => {
    setBusy(true)
    setError(null)
    postDiscard(level)
      .then(() => {
        setConflicts([])
        onDiscarded()
      })
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setBusy(false))
  }, [level, onDiscarded])

  const handleResolve = useCallback(
    (picks: Record<string, 'mine' | 'theirs'>) => runSave(mapToSaveResolutions(picks)),
    [runSave],
  )

  // "discard just this actor" (spec's own escape hatch, needing the Task 3 /discard extension):
  // drops ONE conflicting actor's stage without touching any other staged/conflicting actor. Once
  // this is the LAST remaining conflict, the level's whole stage is now empty -- onDiscarded().
  const handleDiscardConflictActor = useCallback(
    (name: string) => {
      setBusy(true)
      setError(null)
      // Read `conflicts` from closure (this callback is re-created whenever it changes, via the
      // dependency array below), not a functional `setConflicts` updater -- calling `onDiscarded`
      // (a side effect) from inside a state-updater function risks a double-fire under React
      // StrictMode's deliberate double-invocation of updaters.
      postDiscard(level, [name])
        .then(() => {
          const next = conflicts.filter((c) => c.name !== name)
          setConflicts(next)
          onActorDiscarded?.(name)
          if (next.length === 0) onDiscarded()
        })
        .catch((e: unknown) => setError(String(e)))
        .finally(() => setBusy(false))
    },
    [level, onDiscarded, onActorDiscarded, conflicts],
  )

  if (stagedNames.size === 0 && conflicts.length === 0) return null

  return (
    <div className="save-bar">
      <div className="save-bar-actions">
        <span className="save-bar-count">
          {stagedNames.size} staged move{stagedNames.size === 1 ? '' : 's'}
        </span>
        <button type="button" onClick={handleSave} disabled={busy || conflicts.length > 0}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        {/* Gated on `conflicts.length > 0` too (review finding): while a conflict is open, the
            ONLY ways to clear it are resolving every row via ConflictResolver or the per-actor
            discard escape hatch below -- the whole-level Discard button must not be a one-click
            bypass of the mandatory conflict UI. */}
        <button type="button" onClick={handleDiscard} disabled={busy || conflicts.length > 0}>
          Discard
        </button>
      </div>
      {error && <div className="save-bar-error">{error}</div>}
      {conflicts.length > 0 && (
        <div className="save-bar-conflict">
          <ConflictResolver
            conflicts={conflicts}
            resolutionLabels={SAVE_RESOLUTION_LABELS}
            onResolve={handleResolve}
          />
          <div className="save-bar-conflict-discard-list">
            <p>Or discard one actor&apos;s staged edit, leaving the rest staged:</p>
            {conflicts.map((c) => (
              <button
                key={c.name}
                type="button"
                disabled={busy}
                onClick={() => handleDiscardConflictActor(c.name)}
              >
                Discard {c.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
