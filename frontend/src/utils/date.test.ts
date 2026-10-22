import { describe, expect, it } from 'vitest'
import { isStaleTimestamp, PREDICTION_STALE_AFTER_HOURS } from './date'

const NOW = Date.parse('2026-10-20T00:00:00Z')

describe('isStaleTimestamp', () => {
  it('uses a 24-hour threshold by default', () => {
    expect(PREDICTION_STALE_AFTER_HOURS).toBe(24)
  })

  it('is fresh inside the threshold', () => {
    expect(isStaleTimestamp('2026-10-19T12:00:00Z', 24, NOW)).toBe(false)
  })

  it('is exactly 24 hours old and still fresh at the boundary', () => {
    expect(isStaleTimestamp('2026-10-19T00:00:00Z', 24, NOW)).toBe(false)
  })

  it('is stale beyond the threshold', () => {
    expect(isStaleTimestamp('2026-10-18T23:59:59Z', 24, NOW)).toBe(true)
  })

  it('treats unparseable timestamps as stale', () => {
    expect(isStaleTimestamp('not-a-date', 24, NOW)).toBe(true)
  })
})
