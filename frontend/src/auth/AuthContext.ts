import { createContext } from 'react'
import type { LoginCredentials, User } from '../types/auth'

export interface AuthContextValue {
  user: User | null
  token: string | null
  isLoading: boolean
  sessionError: string | null
  login: (credentials: LoginCredentials) => Promise<User>
  logout: () => void
  retrySession: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
