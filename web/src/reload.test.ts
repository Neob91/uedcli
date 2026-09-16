import { beforeEach, describe, expect, it, vi } from 'vitest'

const { openChangesAvailableSocketMock, fakeSocket } = vi.hoisted(() => {
  const fakeSocket = { close: vi.fn() }
  return {
    openChangesAvailableSocketMock: vi.fn(),
    fakeSocket,
  }
})

vi.mock('./api', () => ({
  openChangesAvailableSocket: openChangesAvailableSocketMock,
}))

// Imported AFTER the mock so `subscribeChangesAvailable` picks up the mocked `./api`.
const { subscribeChangesAvailable } = await import('./reload')

beforeEach(() => {
  openChangesAvailableSocketMock.mockReset()
  fakeSocket.close.mockReset()
  openChangesAvailableSocketMock.mockImplementation((onChanged: () => void) => {
    // Capture the push trigger on the returned "socket" so tests can fire it manually.
    ;(fakeSocket as unknown as { trigger: () => void }).trigger = onChanged
    return fakeSocket
  })
})

describe('subscribeChangesAvailable', () => {
  it('calls onChangesAvailable for every pushed message -- no fetch, no auto-refetch', () => {
    const onChangesAvailable = vi.fn()
    subscribeChangesAvailable(onChangesAvailable)
    expect(onChangesAvailable).not.toHaveBeenCalled()

    ;(fakeSocket as unknown as { trigger: () => void }).trigger()
    expect(onChangesAvailable).toHaveBeenCalledTimes(1)

    ;(fakeSocket as unknown as { trigger: () => void }).trigger()
    expect(onChangesAvailable).toHaveBeenCalledTimes(2)
  })

  it('unsubscribe closes the underlying socket', () => {
    const sub = subscribeChangesAvailable(() => {})
    sub.unsubscribe()
    expect(fakeSocket.close).toHaveBeenCalledTimes(1)
  })
})
