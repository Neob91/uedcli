import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** A minimal fake `WebSocket` -- just enough surface for `reload.ts`, which only calls
 * `addEventListener('close', ...)` and `close()` on whatever `openChangesAvailableSocket` (mocked
 * below) hands it back. `fireClose(code)` simulates the server (or a dropped connection) closing
 * it -- `code` defaults to 1006 (an ordinary abnormal-closure code a real browser would report for
 * a dropped connection), matching every pre-existing call site that doesn't care about the code. */
function makeFakeSocket() {
  const closeListeners: Array<(event: { code: number }) => void> = []
  return {
    addEventListener: vi.fn((type: string, cb: (event: { code: number }) => void) => {
      if (type === 'close') closeListeners.push(cb)
    }),
    close: vi.fn(),
    fireClose: (code = 1006) => closeListeners.forEach((cb) => cb({ code })),
  }
}

const { openChangesAvailableSocketMock } = vi.hoisted(() => ({ openChangesAvailableSocketMock: vi.fn() }))

vi.mock('./api', () => ({
  openChangesAvailableSocket: openChangesAvailableSocketMock,
}))

// Imported AFTER the mock so `subscribeChangesAvailable` picks up the mocked `./api`.
const { subscribeChangesAvailable } = await import('./reload')

type Call = {
  sessionId: string
  claimToken: string
  onChanged: () => void
  onSuperseded: () => void
  socket: ReturnType<typeof makeFakeSocket>
}
let calls: Call[]

beforeEach(() => {
  vi.useFakeTimers()
  calls = []
  openChangesAvailableSocketMock.mockReset()
  openChangesAvailableSocketMock.mockImplementation(
    (sessionId: string, claimToken: string, onChanged: () => void, onSuperseded: () => void) => {
      const socket = makeFakeSocket()
      calls.push({ sessionId, claimToken, onChanged, onSuperseded, socket })
      return socket
    },
  )
})

afterEach(() => {
  vi.useRealTimers()
})

describe('subscribeChangesAvailable', () => {
  it('opens the socket with the given session id and claim token', () => {
    subscribeChangesAvailable('sess-1', 'tok-1', vi.fn(), vi.fn())

    expect(calls).toHaveLength(1)
    expect(calls[0].sessionId).toBe('sess-1')
    expect(calls[0].claimToken).toBe('tok-1')
  })

  it('calls onChangesAvailable for every pushed "changes_available" message -- no fetch, no auto-refetch', () => {
    const onChangesAvailable = vi.fn()
    subscribeChangesAvailable('sess-1', 'tok-1', onChangesAvailable, vi.fn())

    calls[0].onChanged()
    expect(onChangesAvailable).toHaveBeenCalledTimes(1)
    calls[0].onChanged()
    expect(onChangesAvailable).toHaveBeenCalledTimes(2)
  })

  it('an explicit "superseded" push calls onSuperseded and does not reconnect', () => {
    const onSuperseded = vi.fn()
    subscribeChangesAvailable('sess-1', 'tok-1', vi.fn(), onSuperseded)

    calls[0].onSuperseded()
    expect(onSuperseded).toHaveBeenCalledTimes(1)

    // The server closes the socket right after sending "superseded" -- that close must not also
    // trigger a reconnect (the session is genuinely gone, not just a dropped connection).
    calls[0].socket.fireClose()
    vi.advanceTimersByTime(10_000)
    expect(openChangesAvailableSocketMock).toHaveBeenCalledTimes(1)
  })

  it('an ordinary close with NO prior "superseded" message does not show the takeover, and instead reconnects', () => {
    const onSuperseded = vi.fn()
    subscribeChangesAvailable('sess-1', 'tok-1', vi.fn(), onSuperseded)

    calls[0].socket.fireClose()
    expect(onSuperseded).not.toHaveBeenCalled()
    // Not immediately -- the reconnect is delayed, not instant.
    expect(openChangesAvailableSocketMock).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(5000)

    // A genuinely NEW socket got constructed -- this is the reconnect attempt, not merely the
    // absence of a takeover.
    expect(openChangesAvailableSocketMock).toHaveBeenCalledTimes(2)
    expect(calls[1].sessionId).toBe('sess-1')
    expect(calls[1].claimToken).toBe('tok-1')
  })

  it('a close with code 4001 (unknown session or missing claim) does not reconnect', () => {
    const onSuperseded = vi.fn()
    subscribeChangesAvailable('sess-1', 'tok-1', vi.fn(), onSuperseded)

    // 4001 means the request itself was bad -- no prior "superseded" message, since the server
    // never even accepted the connection to send one on this path.
    calls[0].socket.fireClose(4001)
    expect(onSuperseded).not.toHaveBeenCalled()

    vi.advanceTimersByTime(10_000)

    // Retrying with the exact same sessionId/claimToken could never succeed -- no new socket.
    expect(openChangesAvailableSocketMock).toHaveBeenCalledTimes(1)
  })

  it('a close with an ordinary code (e.g. 1006, a dropped connection) still reconnects', () => {
    subscribeChangesAvailable('sess-1', 'tok-1', vi.fn(), vi.fn())

    calls[0].socket.fireClose(1006)
    expect(openChangesAvailableSocketMock).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(5000)

    expect(openChangesAvailableSocketMock).toHaveBeenCalledTimes(2)
  })

  it('unsubscribe closes the current socket and suppresses any further reconnect', () => {
    const sub = subscribeChangesAvailable('sess-1', 'tok-1', vi.fn(), vi.fn())

    sub.unsubscribe()
    expect(calls[0].socket.close).toHaveBeenCalledTimes(1)

    // A close firing after unsubscribe (the socket closing in response to our own .close() call)
    // must not schedule a reconnect either.
    calls[0].socket.fireClose()
    vi.advanceTimersByTime(10_000)
    expect(openChangesAvailableSocketMock).toHaveBeenCalledTimes(1)
  })
})
