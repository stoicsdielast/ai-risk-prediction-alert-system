import { apiRequest } from './client'
import type { User } from '../types/auth'

export function getPendingUsers(token: string): Promise<User[]> {
  return apiRequest<User[]>('/api/admin/users/pending', { token })
}

export function approveUser(token: string, userId: number): Promise<User> {
  return apiRequest<User>(`/api/admin/users/${userId}/approve`, {
    method: 'PATCH',
    token,
  })
}

export function rejectUser(token: string, userId: number): Promise<User> {
  return apiRequest<User>(`/api/admin/users/${userId}/reject`, {
    method: 'PATCH',
    token,
  })
}
