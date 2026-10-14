import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { getCurrentUser, loginUser } from '../api/auth'
import { ApiError } from '../api/client'
import type { LoginCredentials, User } from '../types/auth'
import { AuthContext } from './AuthContext'

const TOKEN_STORAGE_KEY = 'fiji-flood-access-token'

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [token, setToken] = useState<string | null>(() =>
    sessionStorage.getItem(TOKEN_STORAGE_KEY),
  )
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(Boolean(token))
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [sessionCheck, setSessionCheck] = useState(0)

  const logout = useCallback((reason?: string) => {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY)
    setToken(null)
    setUser(null)
    setSessionError(reason ?? null)
    setIsLoading(false)
  }, [])

  const retrySession = useCallback(() => {
    if (!token) return
    setSessionError(null)
    setIsLoading(true)
    setSessionCheck((currentCheck) => currentCheck + 1)
  }, [token])

  useEffect(() => {
    if (!token) {
      setIsLoading(false)
      return
    }

    let isCurrent = true
    setIsLoading(true)
    setSessionError(null)

    getCurrentUser(token)
      .then((currentUser) => {
        if (isCurrent) setUser(currentUser)
      })
      .catch((caughtError: unknown) => {
        if (!isCurrent) return

        if (
          caughtError instanceof ApiError &&
          (caughtError.status === 401 || caughtError.status === 403)
        ) {
          logout()
          return
        }

        setUser(null)
        setSessionError(
          caughtError instanceof ApiError
            ? caughtError.message
            : 'Unable to check your session. Please try again.',
        )
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [logout, sessionCheck, token])

  const login = useCallback(
    async (credentials: LoginCredentials): Promise<User> => {
      const tokenResponse = await loginUser(credentials)
      const currentUser = await getCurrentUser(tokenResponse.access_token)

      sessionStorage.setItem(TOKEN_STORAGE_KEY, tokenResponse.access_token)
      setToken(tokenResponse.access_token)
      setUser(currentUser)
      setSessionError(null)
      return currentUser
    },
    [],
  )

  const value = useMemo(
    () => ({
      user,
      token,
      isLoading,
      sessionError,
      login,
      logout,
      retrySession,
    }),
    [isLoading, login, logout, retrySession, sessionError, token, user],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
