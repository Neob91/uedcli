import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SaveBar } from './SaveBar'

const postSave = vi.fn()
const postDiscard = vi.fn()

vi.mock('../api', () => ({
  postSave: (...args: unknown[]) => postSave(...args),
  postDiscard: (...args: unknown[]) => postDiscard(...args),
  // Mirrors api.ts's own real implementation (Task 17) -- SaveBar.tsx imports this for real, and
  // this mock replaces the whole module, so it must supply a working one too.
  isSupersededError: (e: unknown) => typeof e === 'object' && e !== null && (e as { status?: number }).status === 409,
}))

afterEach(() => {
  cleanup()
  postSave.mockReset()
  postDiscard.mockReset()
})

describe('SaveBar', () => {
  it('renders nothing with no staged names', () => {
    const { container } = render(
      <SaveBar level="TestLevel" stagedNames={new Set()} onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )
    expect(container.innerHTML).toBe('')
  })

  // Bug found post-merge: a plain Rebuild with nothing staged used to hide this whole component,
  // leaving no way to click Save to promote that rebuild's pin to the level.
  it('renders a bare Save button (no count, no Discard) when hasBuildPin is true but nothing is staged', () => {
    render(
      <SaveBar level="TestLevel" stagedNames={new Set()} hasBuildPin onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Discard' })).toBeNull()
    expect(screen.queryByText(/Unsaved:/)).toBeNull()
  })

  it('still renders nothing when hasBuildPin is false and nothing is staged', () => {
    const { container } = render(
      <SaveBar level="TestLevel" stagedNames={new Set()} hasBuildPin={false} onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('clicking the bare Save button (hasBuildPin, nothing staged) calls postSave with no resolutions', async () => {
    postSave.mockResolvedValue({ applied: [], conflicts: [] })
    const onSaved = vi.fn()
    render(
      <SaveBar level="TestLevel" stagedNames={new Set()} hasBuildPin onSaved={onSaved} onDiscarded={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(postSave).toHaveBeenCalledWith('TestLevel', {}))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('renders Save/Discard buttons with staged names', () => {
    render(
      <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Discard' })).toBeTruthy()
  })

  // Copy fix (Task 17): user-facing copy says "unsaved," never "staged" -- the spec's own naming
  // decision. No literal "Stage"-labeled button exists anywhere in this codebase (staging happens
  // via drag gestures, not a button click), so this is the one real user-facing count to fix.
  it('labels the staged count as "Unsaved: N", never "staged"', () => {
    render(
      <SaveBar level="TestLevel" stagedNames={new Set(['Light0', 'Light1'])} onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )
    expect(screen.getByText('Unsaved: 2')).toBeTruthy()
    expect(screen.queryByText(/staged/i)).toBeNull()
  })

  it('clicking Save calls postSave and, on a clean apply, calls onSaved', async () => {
    postSave.mockResolvedValue({ applied: ['Light0'], conflicts: [] })
    const onSaved = vi.fn()
    render(
      <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={onSaved} onDiscarded={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(postSave).toHaveBeenCalledWith('TestLevel', {}))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('clicking Discard calls postDiscard with no actors and calls onDiscarded', async () => {
    postDiscard.mockResolvedValue({ status: 'ok' })
    const onDiscarded = vi.fn()
    render(
      <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={onDiscarded} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))

    await waitFor(() => expect(postDiscard).toHaveBeenCalledWith('TestLevel'))
    await waitFor(() => expect(onDiscarded).toHaveBeenCalled())
  })

  it('a postSave response with conflicts mounts ConflictResolver and blocks Save until resolved', async () => {
    postSave.mockResolvedValueOnce({
      applied: [],
      conflicts: [{ name: 'Light0', staged_location: [10, 0, 0], trunk_location: [20, 0, 0] }],
    })
    const onSaved = vi.fn()
    render(
      <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={onSaved} onDiscarded={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByText('Light0')).toBeTruthy())

    // Save must NOT be clickable again while a conflict is pending.
    const saveButton = screen.getByRole('button', { name: 'Save' })
    expect(saveButton.hasAttribute('disabled')).toBe(true)
    expect(onSaved).not.toHaveBeenCalled()

    // Resolve it: pick "Keep my move" for Light0, confirm.
    postSave.mockResolvedValueOnce({ applied: ['Light0'], conflicts: [] })
    fireEvent.click(screen.getByLabelText('Keep my move'))
    fireEvent.click(screen.getByRole('button', { name: /apply/i }))

    await waitFor(() => expect(postSave).toHaveBeenLastCalledWith('TestLevel', { Light0: 'staged' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(screen.queryByText('Light0')).toBeNull()
  })

  it('discarding one conflicting actor calls postDiscard(level, [name]) and removes that row', async () => {
    postSave.mockResolvedValueOnce({
      applied: [],
      conflicts: [
        { name: 'Light0', staged_location: [10, 0, 0], trunk_location: [20, 0, 0] },
        { name: 'Light1', staged_location: [1, 2, 3], trunk_location: [4, 5, 6] },
      ],
    })
    const onDiscarded = vi.fn()
    render(
      <SaveBar level="TestLevel" stagedNames={new Set(['Light0', 'Light1'])} onSaved={vi.fn()} onDiscarded={onDiscarded} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByText('Light0')).toBeTruthy())

    postDiscard.mockResolvedValue({ status: 'ok' })
    fireEvent.click(screen.getByRole('button', { name: /discard light0/i }))

    await waitFor(() => expect(postDiscard).toHaveBeenCalledWith('TestLevel', ['Light0']))
    await waitFor(() => expect(screen.queryByText('Light0')).toBeNull())
    // Light1's conflict is still pending -- discarding one row is not a whole-level discard.
    expect(screen.getByText('Light1')).toBeTruthy()
    expect(onDiscarded).not.toHaveBeenCalled()
  })

  // Critical 2, final review fix wave: the per-actor conflict-discard escape hatch used to have no
  // way to tell App.tsx to drop THAT actor's client-rendered staged position -- App only found out
  // about the whole-level `onDiscarded` (which never fires here, since Light1 is still staged), so
  // the discarded actor's stale offset would keep rendering forever. `onActorDiscarded` closes that.
  it('calls onActorDiscarded(name) for the per-actor discard escape hatch, distinct from onDiscarded', async () => {
    postSave.mockResolvedValueOnce({
      applied: [],
      conflicts: [
        { name: 'Light0', staged_location: [10, 0, 0], trunk_location: [20, 0, 0] },
        { name: 'Light1', staged_location: [1, 2, 3], trunk_location: [4, 5, 6] },
      ],
    })
    const onDiscarded = vi.fn()
    const onActorDiscarded = vi.fn()
    render(
      <SaveBar
        level="TestLevel"
        stagedNames={new Set(['Light0', 'Light1'])}
        onSaved={vi.fn()}
        onDiscarded={onDiscarded}
        onActorDiscarded={onActorDiscarded}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByText('Light0')).toBeTruthy())

    postDiscard.mockResolvedValue({ status: 'ok' })
    fireEvent.click(screen.getByRole('button', { name: /discard light0/i }))

    await waitFor(() => expect(onActorDiscarded).toHaveBeenCalledWith('Light0'))
    expect(onDiscarded).not.toHaveBeenCalled() // Light1 is still staged -- not a whole-level clear
  })

  it('the whole-level Discard button is disabled while a conflict is open, and re-enables once it clears', async () => {
    postSave.mockResolvedValueOnce({
      applied: [],
      conflicts: [{ name: 'Light0', staged_location: [10, 0, 0], trunk_location: [20, 0, 0] }],
    })
    render(
      <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByText('Light0')).toBeTruthy())

    // The plain whole-level Discard button must NOT be a one-click bypass of the mandatory
    // conflict UI -- it's disabled while any conflict is open, and clicking it (even forced past
    // the `disabled` attribute) must not call the whole-level postDiscard(level) with no actors.
    const discardButton = screen.getByRole('button', { name: 'Discard' })
    expect(discardButton.hasAttribute('disabled')).toBe(true)
    fireEvent.click(discardButton)
    expect(postDiscard).not.toHaveBeenCalledWith('TestLevel')

    // Resolve the only remaining conflict -- the whole-level Discard button re-enables once
    // `conflicts` is empty again.
    postSave.mockResolvedValueOnce({ applied: ['Light0'], conflicts: [] })
    fireEvent.click(screen.getByLabelText('Keep my move'))
    fireEvent.click(screen.getByRole('button', { name: /apply/i }))
    await waitFor(() => expect(screen.queryByText('Light0')).toBeNull())

    expect(screen.getByRole('button', { name: 'Discard' }).hasAttribute('disabled')).toBe(false)
  })

  it('labels the per-actor conflict-discard escape hatch as "unsaved," never "staged"', async () => {
    postSave.mockResolvedValueOnce({
      applied: [],
      conflicts: [{ name: 'Light0', staged_location: [10, 0, 0], trunk_location: [20, 0, 0] }],
    })
    render(
      <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByText('Light0')).toBeTruthy())

    expect(screen.getByText("Or discard one actor's unsaved edit, leaving the rest unsaved:")).toBeTruthy()
    expect(screen.queryByText(/staged/i)).toBeNull()
  })

  // Task 17: a 409 from postSave/postDiscard means this session's claim was taken by another
  // window (or it was deleted) -- the same takeover the `/ws` "superseded" push shows. SaveBar
  // reports this through `onSuperseded` instead of its own local error banner.
  describe('superseded (409) handling', () => {
    it('a 409 from postSave calls onSuperseded, not the local error banner', async () => {
      const supersededError = Object.assign(new Error('sess-1: session superseded'), { status: 409 })
      postSave.mockRejectedValueOnce(supersededError)
      const onSuperseded = vi.fn()
      render(
        <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={vi.fn()} onSuperseded={onSuperseded} />,
      )

      fireEvent.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(onSuperseded).toHaveBeenCalledTimes(1))
      expect(screen.queryByText(/session superseded/)).toBeNull()
    })

    it('a 409 from postDiscard (whole-level Discard) calls onSuperseded', async () => {
      const supersededError = Object.assign(new Error('sess-1: session superseded'), { status: 409 })
      postDiscard.mockRejectedValueOnce(supersededError)
      const onSuperseded = vi.fn()
      render(
        <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={vi.fn()} onSuperseded={onSuperseded} />,
      )

      fireEvent.click(screen.getByRole('button', { name: 'Discard' }))

      await waitFor(() => expect(onSuperseded).toHaveBeenCalledTimes(1))
    })

    it('a non-409 error still shows the local error banner, not onSuperseded', async () => {
      postSave.mockRejectedValueOnce(new Error('sess-1: level not found'))
      const onSuperseded = vi.fn()
      render(
        <SaveBar level="TestLevel" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={vi.fn()} onSuperseded={onSuperseded} />,
      )

      fireEvent.click(screen.getByRole('button', { name: 'Save' }))

      await waitFor(() => expect(screen.getByText(/level not found/)).toBeTruthy())
      expect(onSuperseded).not.toHaveBeenCalled()
    })
  })

  it('resets local conflict/busy/error state when the level prop changes', async () => {
    postSave.mockResolvedValueOnce({
      applied: [],
      conflicts: [{ name: 'Light0', staged_location: [10, 0, 0], trunk_location: [20, 0, 0] }],
    })
    const { rerender } = render(
      <SaveBar level="LevelA" stagedNames={new Set(['Light0'])} onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(screen.getByText('Light0')).toBeTruthy())
    expect(screen.getByRole('button', { name: 'Save' }).hasAttribute('disabled')).toBe(true)

    // Switch levels while the conflict banner is still open (App.tsx's own `handleSwitchLevel`
    // resets its sibling `loadConflicts` state the same way on this same signal). `stagedNames`
    // stays non-empty (a different actor, staged fresh on the new level) so the bar keeps
    // rendering -- proving the Save button's re-enabled state comes from the conflict state
    // actually clearing, not merely from the component unmounting.
    rerender(
      <SaveBar level="LevelB" stagedNames={new Set(['OtherActor'])} onSaved={vi.fn()} onDiscarded={vi.fn()} />,
    )

    // The stale conflict from LevelA must not linger -- ConflictResolver's rows are gone, and
    // neither button is disabled by a conflict that no longer applies to this level.
    expect(screen.queryByText('Light0')).toBeNull()
    expect(screen.getByRole('button', { name: 'Save' }).hasAttribute('disabled')).toBe(false)
    expect(screen.getByRole('button', { name: 'Discard' }).hasAttribute('disabled')).toBe(false)
  })
})
