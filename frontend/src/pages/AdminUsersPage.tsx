import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { approveUser, getPendingUsers, rejectUser } from '../api/admin'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Alert } from '../components/Alert'
import type { User } from '../types/auth'

type ReviewAction = 'approve' | 'reject'

export function AdminUsersPage() {
  const { token, logout } = useAuth()
  const navigate = useNavigate()
  const [users, setUsers] = useState<User[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [actionUserId, setActionUserId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const handleApiError = useCallback(
    (caughtError: unknown) => {
      if (
        caughtError instanceof ApiError &&
        (caughtError.status === 401 || caughtError.status === 403)
      ) {
        logout()
        navigate('/login', { replace: true })
        return
      }

      setError(
        caughtError instanceof ApiError
          ? caughtError.message
          : 'Unable to complete that request. Please try again.',
      )
    },
    [logout, navigate],
  )

  useEffect(() => {
    if (!token) return

    let isCurrent = true
    setIsLoading(true)

    getPendingUsers(token)
      .then((pendingUsers) => {
        if (isCurrent) setUsers(pendingUsers)
      })
      .catch((caughtError: unknown) => {
        if (isCurrent) handleApiError(caughtError)
      })
      .finally(() => {
        if (isCurrent) setIsLoading(false)
      })

    return () => {
      isCurrent = false
    }
  }, [handleApiError, token])

  const reviewUser = async (user: User, action: ReviewAction) => {
    if (!token) return

    const actionLabel = action === 'approve' ? 'Approve' : 'Reject'
    const roleLabel = user.role === 'MET_ADMIN' ? 'MET administrator' : 'Community'

    if (
      !window.confirm(
        `${actionLabel} this account request?\n\n` +
          `${user.name}\n${user.email}\nRequested role: ${roleLabel}`,
      )
    ) {
      return
    }

    setError(null)
    setSuccess(null)
    setActionUserId(user.id)

    try {
      const updatedUser =
        action === 'approve'
          ? await approveUser(token, user.id)
          : await rejectUser(token, user.id)

      setUsers((currentUsers) =>
        currentUsers.filter((pendingUser) => pendingUser.id !== user.id),
      )
      setSuccess(
        `${updatedUser.name}'s account was ${
          action === 'approve' ? 'approved' : 'rejected'
        }.`,
      )
    } catch (caughtError) {
      handleApiError(caughtError)
    } finally {
      setActionUserId(null)
    }
  }

  return (
    <div className="page-stack">
      <section className="page-heading page-heading--admin">
        <div>
          <span className="eyebrow">MET administration</span>
          <h1>Pending account review</h1>
          <p>Review each request carefully before granting system access.</p>
        </div>
        <div className="pending-count">
          <strong>{users.length}</strong>
          <span>pending {users.length === 1 ? 'request' : 'requests'}</span>
        </div>
      </section>

      {error && <Alert tone="error">{error}</Alert>}
      {success && <Alert tone="success">{success}</Alert>}

      <section className="review-panel">
        <div className="review-panel__header">
          <div>
            <h2>Access requests</h2>
            <p>Only approved and active users can sign in.</p>
          </div>
          <span className="security-note">Server-enforced permissions</span>
        </div>

        {isLoading ? (
          <div className="panel-state" aria-live="polite">
            <span className="spinner" />
            <p>Loading pending accounts…</p>
          </div>
        ) : users.length === 0 ? (
          <div className="panel-state panel-state--empty">
            <div className="empty-mark" aria-hidden="true">✓</div>
            <h3>All caught up</h3>
            <p>There are no pending account requests right now.</p>
          </div>
        ) : (
          <div className="review-list">
            {users.map((user) => (
              <article className="review-row" key={user.id}>
                <div className="review-row__avatar" aria-hidden="true">
                  {user.name.slice(0, 1).toUpperCase()}
                </div>
                <div className="review-row__identity">
                  <strong>{user.name}</strong>
                  <span>{user.email}</span>
                </div>
                <div className="review-row__meta">
                  <span className={`role-badge role-badge--${user.role.toLowerCase()}`}>
                    {user.role === 'MET_ADMIN' ? 'MET admin' : 'Community'}
                  </span>
                  <small>Request #{user.id}</small>
                </div>
                <div className="review-row__actions">
                  <button
                    className="button button--danger-quiet"
                    type="button"
                    disabled={actionUserId !== null}
                    aria-label={`Reject account for ${user.name}`}
                    onClick={() => reviewUser(user, 'reject')}
                  >
                    Reject
                  </button>
                  <button
                    className="button button--approve"
                    type="button"
                    disabled={actionUserId !== null}
                    aria-label={`Approve account for ${user.name}`}
                    onClick={() => reviewUser(user, 'approve')}
                  >
                    {actionUserId === user.id ? 'Working…' : 'Approve'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
