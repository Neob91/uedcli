import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createSession,
  fetchAtlas,
  fetchLevels,
  fetchLightmap,
  fetchScene,
  fetchSession,
  fetchSessions,
  fetchStaged,
  fetchStatus,
  isSupersededError,
  postDiscard,
  postLoad,
  postRebuild,
  postSave,
  postStage,
  setClaimToken,
} from './api'

// Task 17: `setClaimToken` is module-level state (not a per-call param -- see api.ts's own doc
// comment on it), so every test that sets one must clean up after itself or leak into an unrelated
// test run later in this file.
afterEach(() => {
  setClaimToken(null)
})

describe('fetchScene', () => {
  it('returns the typed payload from /api/session/<id>/scene', async () => {
    const payload = {
      polys: [
        {
          verts: [0, 0, 0, 1, 0, 0, 1, 1, 0],
          base: [0, 0, 0],
          tu: [1, 0, 0],
          tv: [0, 1, 0],
          pan: [0, 0],
          tex_index: -1,
          masked: false,
          flags: 0,
          lightmap: null,
        },
      ],
      actors: [
        {
          name: 'Room',
          cls: 'Engine.Brush',
          bbox_lo: [0, 0, 0],
          bbox_hi: [1, 1, 1],
          location: [0, 0, 0],
          rotation: [0, 0, 0],
          folder: null,
          labels: [],
          order_value: 'm',
          csg_rank: 1,
          props: [['CsgOper', 'CSG_Subtract']],
        },
      ],
      geometry_pinned: true,
    }
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await fetchScene('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/scene')
  })

  it('rejects with the backend structured-error message on a non-2xx response', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: "session not found: 'bogus'" }), { status: 422 }),
    ) as unknown as typeof fetch

    await expect(fetchScene('bogus')).rejects.toThrow("session not found: 'bogus'")
  })
})

describe('fetchAtlas', () => {
  it('returns the typed atlas payload', async () => {
    const payload = {
      width: 4,
      height: 4,
      manifest: { '0': { x: 0, y: 0, w: 4, h: 4 } },
      png_base64: 'YWJj',
    }
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await fetchAtlas('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/atlas')
  })
})

describe('fetchLightmap', () => {
  it('returns the typed lightmap payload', async () => {
    const payload = {
      width: 8,
      height: 8,
      intensity: 2.5,
      manifest: { '3': { x: 1, y: 1, w: 4, h: 4 } },
      png_base64: 'YWJj',
    }
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await fetchLightmap('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/lightmap')
  })
})

describe('fetchStatus', () => {
  it('returns the typed status payload', async () => {
    const payload = { changes_available: true, geometry_pinned: false, build_status: 'no_build' }
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await fetchStatus('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/status')
  })
})

describe('postLoad', () => {
  it('POSTs a JSON body {resolutions: {}} to the load route by default', async () => {
    const payload = { status: 'ok', conflicts: [] }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await postLoad('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolutions: {} }),
    })
  })

  it('serializes resolutions and returns conflicts', async () => {
    const payload = {
      status: 'ok',
      conflicts: [{ name: 'Light0', staged_location: [1, 2, 3], trunk_location: [4, 5, 6] }],
    }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await postLoad('sess-1', { Light0: 'accept-load' })

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolutions: { Light0: 'accept-load' } }),
    })
  })
})

describe('postStage', () => {
  it('POSTs a JSON body {actors} to the stage route', async () => {
    const payload = { staged: ['Light0', 'Light1'] }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await postStage('sess-1', { Light0: [1, 2, 3], Light1: [4, 5, 6] })

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actors: { Light0: [1, 2, 3], Light1: [4, 5, 6] } }),
    })
  })
})

describe('postDiscard', () => {
  it('POSTs an empty JSON body to the discard route with no actors', async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ status: 'ok' }), { status: 200 })) as unknown as typeof fetch

    const got = await postDiscard('sess-1')

    expect(got).toEqual({ status: 'ok' })
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/discard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  })

  it('POSTs {actors} to the discard route for a subset discard', async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ status: 'ok' }), { status: 200 })) as unknown as typeof fetch

    const got = await postDiscard('sess-1', ['Light0'])

    expect(got).toEqual({ status: 'ok' })
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/discard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actors: ['Light0'] }),
    })
  })
})

describe('postSave', () => {
  it('POSTs a JSON body {resolutions: {}} to the save route by default', async () => {
    const payload = { applied: ['Light0'], conflicts: [] }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await postSave('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolutions: {} }),
    })
  })

  it('serializes resolutions and returns applied + conflicts', async () => {
    const payload = {
      applied: [],
      conflicts: [{ name: 'Light0', staged_location: [1, 2, 3], trunk_location: [4, 5, 6] }],
    }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await postSave('sess-1', { Light0: 'trunk' })

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolutions: { Light0: 'trunk' } }),
    })
  })
})

describe('fetchStaged', () => {
  it('returns the typed staged-actors payload from /api/session/<id>/staged', async () => {
    const payload = {
      Light0: { staged_location: [1, 2, 3], baseline_location: [0, 0, 0] },
    }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await fetchStaged('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/staged')
  })
})

describe('postRebuild', () => {
  it('POSTs to the session-scoped rebuild route', async () => {
    const payload = { geom_hash: null, light_hash: null }
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await postRebuild('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/rebuild', { method: 'POST' })
  })

  it('rejects with the backend structured-error message on a non-2xx response', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: "session not found: 'bogus'" }), { status: 422 }),
    ) as unknown as typeof fetch

    await expect(postRebuild('bogus')).rejects.toThrow("session not found: 'bogus'")
  })
})

describe('fetchLevels', () => {
  it('returns the typed levels payload from /api/levels', async () => {
    const payload = {
      levels: [
        { name: 'Alpha', active: false },
        { name: 'Beta', active: true },
      ],
      current: 'Beta',
    }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await fetchLevels()

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/levels')
  })
})

describe('createSession', () => {
  it('POSTs to /api/level/<level>/sessions and returns the new session record', async () => {
    const payload = { id: 'sess-1', level: 'Beta', created_at: '2026-09-22T00:00:00Z', claim_token: 'tok-1' }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 201 })) as unknown as typeof fetch

    const got = await createSession('Beta')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/level/Beta/sessions', { method: 'POST' })
  })

  it('rejects with the backend structured-error message on a non-2xx response', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: "level not found: 'bogus'" }), { status: 422 }),
    ) as unknown as typeof fetch

    await expect(createSession('bogus')).rejects.toThrow("level not found: 'bogus'")
  })
})

describe('fetchSession', () => {
  it('GETs /api/session/<id> and returns the resolved record', async () => {
    const payload = {
      id: 'sess-1', level: 'Beta', created_at: '2026-09-22T00:00:00Z',
      last_active_at: '2026-09-22T00:00:01Z', claim_token: 'tok-2',
    }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await fetchSession('sess-1')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1')
  })

  it('rejects on a 404 for an unknown session id', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: "session not found: 'bogus'" }), { status: 404 }),
    ) as unknown as typeof fetch

    await expect(fetchSession('bogus')).rejects.toThrow("session not found: 'bogus'")
  })
})

describe('fetchSessions', () => {
  it('GETs /api/sessions and returns every open session', async () => {
    const payload = {
      sessions: [
        { id: 'sess-1', level: 'Alpha', created_at: '2026-09-22T00:00:00Z', last_active_at: '2026-09-22T00:00:01Z' },
        { id: 'sess-2', level: 'Beta', created_at: '2026-09-22T00:00:02Z', last_active_at: '2026-09-22T00:00:03Z' },
      ],
    }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    const got = await fetchSessions()

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/sessions')
  })
})

// Task 17: every mutating call attaches the session's current claim token as `X-Claim-Token` --
// set once via `setClaimToken` (module-level, see api.ts's own doc comment on why), read by every
// one of `postLoad`/`postRebuild`/`postStage`/`postDiscard`/`postSave`.
describe('claim token header', () => {
  it('postSave attaches X-Claim-Token when a token is set', async () => {
    setClaimToken('tok-1')
    const payload = { applied: ['Light0'], conflicts: [] }
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })) as unknown as typeof fetch

    await postSave('sess-1')

    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Claim-Token': 'tok-1' },
      body: JSON.stringify({ resolutions: {} }),
    })
  })

  it('postStage attaches X-Claim-Token when a token is set', async () => {
    setClaimToken('tok-2')
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ staged: ['Light0'] }), { status: 200 })) as unknown as typeof fetch

    await postStage('sess-1', { Light0: [1, 2, 3] })

    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Claim-Token': 'tok-2' },
      body: JSON.stringify({ actors: { Light0: [1, 2, 3] } }),
    })
  })

  it('postRebuild (no JSON body) still attaches X-Claim-Token when a token is set', async () => {
    setClaimToken('tok-3')
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ geom_hash: null, light_hash: null }), { status: 200 }),
    ) as unknown as typeof fetch

    await postRebuild('sess-1')

    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/rebuild', {
      method: 'POST',
      headers: { 'X-Claim-Token': 'tok-3' },
    })
  })

  it('sends no X-Claim-Token header at all when no token has been set', async () => {
    // No setClaimToken call -- the module starts (and, per the afterEach above, always returns to)
    // a null token. The old exact request shape (no `headers` key at all for postRebuild, no
    // `X-Claim-Token` for postSave) must be preserved unchanged for a caller with no session yet.
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ geom_hash: null, light_hash: null }), { status: 200 }),
    ) as unknown as typeof fetch

    await postRebuild('sess-1')

    expect(globalThis.fetch).toHaveBeenCalledWith('/api/session/sess-1/rebuild', { method: 'POST' })
  })
})

describe('isSupersededError', () => {
  it('is true for an Error carrying status 409 (a mutating call rejected by request())', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: 'session superseded' }), { status: 409 }),
    ) as unknown as typeof fetch

    try {
      await postSave('sess-1')
      expect.unreachable('postSave should have rejected on the 409 response')
    } catch (e) {
      expect(isSupersededError(e)).toBe(true)
    }
  })

  it('is false for any other status, and for a non-error value', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: 'level not found' }), { status: 422 }),
    ) as unknown as typeof fetch

    try {
      await postSave('sess-1')
      expect.unreachable('postSave should have rejected on the 422 response')
    } catch (e) {
      expect(isSupersededError(e)).toBe(false)
    }
    expect(isSupersededError(new Error('plain error, no status'))).toBe(false)
    expect(isSupersededError(null)).toBe(false)
    expect(isSupersededError('a string')).toBe(false)
  })
})
