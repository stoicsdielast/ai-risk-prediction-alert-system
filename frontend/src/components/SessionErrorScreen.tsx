import { useAuth } from '../auth/useAuth'
import { Brand } from './Brand'

export function SessionErrorScreen() {
  const { sessionError, retrySession, logout } = useAuth()

  return (
    <main className="session-error-screen">
      <Brand />
      <div className="session-error-card" role="alert">
        <span className="eyebrow">Connection interrupted</span>
        <h1>We could not check your session.</h1>
        <p>{sessionError || 'The backend may be temporarily unavailable.'}</p>
        <div>
          <button className="button button--primary" type="button" onClick={retrySession}>
            Try again
          </button>
          <button className="button button--secondary" type="button" onClick={() => logout()}>
            Return to sign in
          </button>
        </div>
      </div>
    </main>
  )
}
