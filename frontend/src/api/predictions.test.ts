import { afterEach, describe, expect, it, vi } from 'vitest'
import { runReplay } from './predictions'
import type { ReplayExample } from './predictions'

const example = { id: 'normal', station: { station_id: 'A' }, mode: 'historical_replay', country: 'Bangladesh',
  feature_date: '2024-05-01', as_of: '2024-05-01T23:59:59Z', features: { rainfall_local_mm: 2 },
  observed_proxy_label: 1, expected_probability: .9 } as unknown as ReplayExample

afterEach(() => vi.unstubAllGlobals())

describe('research API contract', () => {
  it('sends only inference fields with authentication', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok', research_mode: true, country: 'Bangladesh', mode: 'historical_replay', probability: .8, presentation_tier: 'VERY_HIGH' })))
    vi.stubGlobal('fetch', fetch)
    await runReplay(example, 'token')
    const options = fetch.mock.calls[0][1]
    expect(JSON.parse(options.body)).toEqual({ mode: 'historical_replay', country: 'Bangladesh', station_id: 'A', feature_date: example.feature_date, as_of: example.as_of, features: example.features })
    expect(options.headers.get('Authorization')).toBe('Bearer token')
  })

  it('rejects a missing score and any response claiming a Fiji forecast', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok', research_mode: true, country: 'Fiji', probability: null })))
    vi.stubGlobal('fetch', fetch)
    await expect(runReplay(example, 'token')).rejects.toThrow('Invalid research prediction')
  })
})
