import { describe, expect, it, vi } from 'vitest'

import { fetchAtlas, fetchLevels, fetchLightmap, fetchScene, fetchStatus, postLoad, postRebuild, switchLevel } from './api'

describe('fetchScene', () => {
  it('returns the typed payload from /api/level/<level>/scene', async () => {
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
          props: [['CsgOper', 'CSG_Subtract']],
        },
      ],
      geometry_pinned: true,
    }
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await fetchScene('TestLevel')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/level/TestLevel/scene')
  })

  it('rejects with the backend structured-error message on a non-2xx response', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: 'level not found: \'bogus\'' }), { status: 422 }),
    ) as unknown as typeof fetch

    await expect(fetchScene('bogus')).rejects.toThrow("level not found: 'bogus'")
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

    const got = await fetchAtlas('TestLevel')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/level/TestLevel/atlas')
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

    const got = await fetchLightmap('TestLevel')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/level/TestLevel/lightmap')
  })
})

describe('fetchStatus', () => {
  it('returns the typed status payload', async () => {
    const payload = { changes_available: true, geometry_pinned: false, build_status: 'no_build' }
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await fetchStatus('TestLevel')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/level/TestLevel/status')
  })
})

describe('postLoad', () => {
  it('POSTs to the load route', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ status: 'ok' }), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await postLoad('TestLevel')

    expect(got).toEqual({ status: 'ok' })
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/level/TestLevel/load', { method: 'POST' })
  })
})

describe('postRebuild', () => {
  it('POSTs to the rebuild route', async () => {
    const payload = { status: 'ok', geom_hash: null, light_hash: null }
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify(payload), { status: 200 }),
    ) as unknown as typeof fetch

    const got = await postRebuild('TestLevel')

    expect(got).toEqual(payload)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/level/TestLevel/rebuild', { method: 'POST' })
  })

  it('rejects with the backend structured-error message on a non-2xx response', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: 'level not found: \'bogus\'' }), { status: 422 }),
    ) as unknown as typeof fetch

    await expect(postRebuild('bogus')).rejects.toThrow("level not found: 'bogus'")
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

describe('switchLevel', () => {
  it('PUTs a JSON body {level: name} to /api/level', async () => {
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ level: 'Beta' }), { status: 200 })) as unknown as typeof fetch

    const got = await switchLevel('Beta')

    expect(got).toEqual({ level: 'Beta' })
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/level', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level: 'Beta' }),
    })
  })

  it('rejects with the backend structured-error message on a non-2xx response', async () => {
    globalThis.fetch = vi.fn(
      async () => new Response(JSON.stringify({ error: "level not found: 'bogus'" }), { status: 422 }),
    ) as unknown as typeof fetch

    await expect(switchLevel('bogus')).rejects.toThrow("level not found: 'bogus'")
  })
})
