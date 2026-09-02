export type UserRole = 'COMMUNITY' | 'MET_ADMIN'

export type AccountStatus = 'PENDING' | 'APPROVED' | 'REJECTED'

export interface User {
  id: number
  name: string
  email: string
  role: UserRole
  status: AccountStatus
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterPayload {
  name: string
  email: string
  password: string
  role: UserRole
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
}
