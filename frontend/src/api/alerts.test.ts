import { afterEach, expect, it, vi } from 'vitest'
import { getAdminAlerts, getPublicAlerts } from './alerts'
import { installAlertApi, sampleAlert } from '../test/alertApiFixture'

afterEach(() => vi.unstubAllGlobals())

it.each([null, [{ id: 4 }], [sampleAlert()], [sampleAlert({ status: 'APPROVED', approved_at: 'invalid' })]])(
  'rejects malformed or unpublished public-feed data (%j)', async (body) => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })))
    await expect(getPublicAlerts()).rejects.toThrow('invalid data')
  },
)

it('includes alerts beyond the first page in admin results', async () => {
  const fixtures = Array.from({ length: 201 }, (_, index) => sampleAlert({ id: index + 1 }))
  const { fetchMock } = installAlertApi(fixtures)
  const rows = await getAdminAlerts('test-token')
  expect(rows).toHaveLength(201)
  expect(
    fetchMock.mock.calls.some(([url]) =>
      String(url).includes('status=PENDING&offset=200&limit=200'),
    ),
  ).toBe(true)
})

it('includes community alerts beyond the first page', async () => {
  const fixtures = Array.from({ length: 201 }, (_, index) =>
    sampleAlert({ id: index + 1, status: 'APPROVED' }),
  )
  const { fetchMock } = installAlertApi(fixtures)
  expect(await getPublicAlerts()).toHaveLength(201)
  expect(
    fetchMock.mock.calls.some(([url]) => String(url).includes('/active?offset=200&limit=200')),
  ).toBe(true)
})
