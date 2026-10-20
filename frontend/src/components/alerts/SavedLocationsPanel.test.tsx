import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/notifications'
import { apiRequest } from '../../api/client'
import { SavedLocationsPanel } from './SavedLocationsPanel'

vi.mock('../../auth/useAuth', () => ({ useAuth: () => ({ token: 'token' }) }))
vi.mock('../../api/notifications')
vi.mock('../../api/client')
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(apiRequest).mockResolvedValue([{ id: 1, name: 'Suva', is_active: true }, { id: 2, name: 'Nadi', is_active: true }])
  vi.mocked(api.getSavedLocations).mockResolvedValue([{ id: 1, name: 'Suva', is_active: true }])
  vi.mocked(api.getNotifications).mockResolvedValue([])
})
it('loads persisted saved locations and manages multiple subscriptions', async () => {
  render(<MemoryRouter><SavedLocationsPanel /></MemoryRouter>)
  expect(await screen.findByLabelText('Suva')).toBeChecked()
  fireEvent.click(screen.getByLabelText('Nadi'))
  await waitFor(() => expect(api.saveLocation).toHaveBeenCalledWith('token', 2, true))
  await waitFor(() => expect(screen.getByLabelText('Suva')).toBeEnabled())
  fireEvent.click(screen.getByLabelText('Suva'))
  await waitFor(() => expect(api.saveLocation).toHaveBeenCalledWith('token', 1, false))
})
it('shows API errors and allows retry', async () => {
  vi.mocked(api.getSavedLocations).mockRejectedValueOnce(new Error('Unavailable'))
  render(<MemoryRouter><SavedLocationsPanel /></MemoryRouter>)
  expect(await screen.findByRole('alert')).toHaveTextContent('Unavailable')
  fireEvent.click(screen.getByText('Refresh saved locations and history'))
  expect(await screen.findByLabelText('Suva')).toBeChecked()
})
