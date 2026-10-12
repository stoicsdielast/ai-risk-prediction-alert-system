import { apiRequest } from './client'
import type {
  LoginCredentials,
  RegisterPayload,
  TokenResponse,
  User,
} from '../types/auth'

export function registerUser(payload: RegisterPayload): Promise<User> {
  return apiRequest<User>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function loginUser(payload: LoginCredentials): Promise<TokenResponse> {
  return apiRequest<TokenResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getCurrentUser(token: string): Promise<User> {
  return apiRequest<User>('/api/auth/me', { token })
}
