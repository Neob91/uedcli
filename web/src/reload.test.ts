import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AtlasPayload, LightmapPayload, ScenePayload } from './api'

const { fetchSceneMock, fetchAtlasMock, fetchLightmapMock, openReloadSocketMock, fakeSocket } = vi.hoisted(() => {
  const fakeSocket = { close: vi.fn() }
  return {
    fetchSceneMock: vi.fn(),
    fetchAtlasMock: vi.fn(),
    fetchLightmapMock: vi.fn(),
    openReloadSocketMock: vi.fn(),
    fakeSocket,
  }
})

vi.mock('./api', () => ({
  fetchScene: fetchSceneMock,
  fetchAtlas: fetchAtlasMock,
  fetchLightmap: fetchLightmapMock,
  openReloadSocket: openReloadSocketMock,
}))

// Imported AFTER the mock so `subscribeReload` picks up the mocked `./api`.
const { subscribeReload } = await import('./reload')

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => {
    resolve = r
  })
  return { promise, resolve }
}

const SCENE: ScenePayload = { polys: [], actors: [] }
const ATLAS: AtlasPayload = { width: 1, height: 1, manifest: {}, png_base64: '' }
const LIGHTMAP: LightmapPayload = { width: 1, height: 1, intensity: 1, manifest: {}, png_base64: '' }

beforeEach(() => {
  fetchSceneMock.mockReset()
  fetchAtlasMock.mockReset()
  fetchLightmapMock.mockReset()
  fetchLightmapMock.mockResolvedValue(LIGHTMAP) // default; tests needing a pending/rejected one override
  openReloadSocketMock.mockReset()
  fakeSocket.close.mockReset()
  openReloadSocketMock.mockImplementation((onReload: () => void) => {
    // Capture the reload trigger on the returned "socket" so tests can fire it manually.
    ;(fakeSocket as unknown as { trigger: () => void }).trigger = onReload
    return fakeSocket
  })
})

describe('subscribeReload', () => {
  it('a reload event triggers a scene+atlas refetch', () => {
    const sceneDeferred = deferred<ScenePayload>()
    const atlasDeferred = deferred<AtlasPayload>()
    fetchSceneMock.mockReturnValue(sceneDeferred.promise)
    fetchAtlasMock.mockReturnValue(atlasDeferred.promise)

    subscribeReload('TestLevel', () => {})
    expect(fetchSceneMock).not.toHaveBeenCalled()

    ;(fakeSocket as unknown as { trigger: () => void }).trigger()
    expect(fetchSceneMock).toHaveBeenCalledWith('TestLevel')
    expect(fetchAtlasMock).toHaveBeenCalledWith('TestLevel')
    expect(fetchLightmapMock).toHaveBeenCalledWith('TestLevel')
  })

  it('does not call onReady until BOTH the scene and atlas refetch resolve (no blank intermediate)', async () => {
    const sceneDeferred = deferred<ScenePayload>()
    const atlasDeferred = deferred<AtlasPayload>()
    fetchSceneMock.mockReturnValue(sceneDeferred.promise)
    fetchAtlasMock.mockReturnValue(atlasDeferred.promise)

    const onReady = vi.fn()
    subscribeReload('TestLevel', onReady)
    ;(fakeSocket as unknown as { trigger: () => void }).trigger()

    await Promise.resolve() // let microtasks settle
    expect(onReady).not.toHaveBeenCalled() // neither has resolved yet -- still showing the stale scene

    sceneDeferred.resolve(SCENE)
    await Promise.resolve()
    expect(onReady).not.toHaveBeenCalled() // only the scene resolved -- still not ready

    atlasDeferred.resolve(ATLAS)
    await Promise.resolve()
    await Promise.resolve()
    expect(onReady).toHaveBeenCalledTimes(1)
    expect(onReady).toHaveBeenCalledWith({ scene: SCENE, atlas: ATLAS, lightmap: LIGHTMAP })
  })

  it('calls onReloadStart immediately, before the refetch resolves', () => {
    fetchSceneMock.mockReturnValue(new Promise(() => {})) // never resolves in this test
    fetchAtlasMock.mockReturnValue(new Promise(() => {}))
    const onReloadStart = vi.fn()

    subscribeReload('TestLevel', () => {}, onReloadStart)
    ;(fakeSocket as unknown as { trigger: () => void }).trigger()

    expect(onReloadStart).toHaveBeenCalledTimes(1)
  })

  it('a failed refetch never calls onReady (the stale scene stays, no crash)', async () => {
    fetchSceneMock.mockReturnValue(Promise.reject(new Error('boom')))
    fetchAtlasMock.mockReturnValue(Promise.resolve(ATLAS))
    const onReady = vi.fn()

    subscribeReload('TestLevel', onReady)
    ;(fakeSocket as unknown as { trigger: () => void }).trigger()
    await Promise.resolve()
    await Promise.resolve()

    expect(onReady).not.toHaveBeenCalled()
  })

  it('ignores a stale reload response that resolves after a newer one', async () => {
    // Two reload pushes can overlap (a cold solve is ~24s): the FIRST fetch resolves AFTER the
    // SECOND. onReady must reflect the newer data and never regress to the stale one.
    const scene1 = deferred<ScenePayload>()
    const atlas1 = deferred<AtlasPayload>()
    const scene2 = deferred<ScenePayload>()
    const atlas2 = deferred<AtlasPayload>()
    fetchSceneMock.mockReturnValueOnce(scene1.promise).mockReturnValueOnce(scene2.promise)
    fetchAtlasMock.mockReturnValueOnce(atlas1.promise).mockReturnValueOnce(atlas2.promise)

    const onReady = vi.fn()
    subscribeReload('TestLevel', onReady)
    const trigger = (fakeSocket as unknown as { trigger: () => void }).trigger
    trigger() // reload push #1
    trigger() // reload push #2, before #1 settles

    const ATLAS_NEW: AtlasPayload = { ...ATLAS, width: 2 }

    // The NEWER push (#2) resolves first.
    scene2.resolve(SCENE)
    atlas2.resolve(ATLAS_NEW)
    await Promise.resolve()
    await Promise.resolve()
    expect(onReady).toHaveBeenCalledTimes(1)
    expect(onReady).toHaveBeenCalledWith({ scene: SCENE, atlas: ATLAS_NEW, lightmap: LIGHTMAP })

    // The OLDER push (#1) resolves after -- must be silently ignored, not applied.
    scene1.resolve(SCENE)
    atlas1.resolve(ATLAS)
    await Promise.resolve()
    await Promise.resolve()
    expect(onReady).toHaveBeenCalledTimes(1) // still just once
  })

  it('unsubscribe closes the underlying socket', () => {
    fetchSceneMock.mockReturnValue(new Promise(() => {}))
    fetchAtlasMock.mockReturnValue(new Promise(() => {}))
    const sub = subscribeReload('TestLevel', () => {})
    sub.unsubscribe()
    expect(fakeSocket.close).toHaveBeenCalledTimes(1)
  })
})
