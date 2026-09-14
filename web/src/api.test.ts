import { describe, expect, it, vi } from 'vitest'

import { fetchAtlas, fetchLightmap, fetchScene } from './api'

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
