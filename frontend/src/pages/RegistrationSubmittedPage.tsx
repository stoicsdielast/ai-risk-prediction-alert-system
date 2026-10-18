import { Link, useLocation } from 'react-router-dom'
import type { UserRole } from '../types/auth'

interface RegistrationState {
  email?: string
  role?: UserRole
}

export function RegistrationSubmittedPage() {
  const location = useLocation()
  const state = location.state as RegistrationState | null

  return (
    <div className="auth-card auth-card--centered">
      <div className="success-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none">
          <path d="m7 12 3.2 3.2L17.5 8" stroke="currentColor" strokeWidth="2" />
        </svg>
      </div>
      <span className="eyebrow">Request received</span>
      <h2>Your account is pending approval</h2>
      <p className="auth-card__lead">
        {state?.email ? (
          <>We created the account for <strong>{state.email}</strong>.</>
        ) : (
          <>Your registration was submitted successfully.</>
        )}{' '}
        A Fiji MET administrator must approve it before you can sign in.
      </p>

      <div className="pending-info">
        <span>What happens next?</span>
        <ol>
          <li>An approved MET administrator reviews your request.</li>
          <li>Your status changes from PENDING to APPROVED or REJECTED.</li>
          <li>Once approved, return here and sign in.</li>
        </ol>
      </div>

      <Link className="button button--primary button--full" to="/login">
        Go to sign in
      </Link>
      <Link className="quiet-link" to="/">Back to welcome</Link>
    </div>
  )
}
