import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { registerUser } from '../api/auth'
import { ApiError } from '../api/client'
import { Alert } from '../components/Alert'
import { FormField } from '../components/FormField'
import type { UserRole } from '../types/auth'

export function RegisterPage() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [role, setRole] = useState<UserRole>('COMMUNITY')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError(null)

    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setIsSubmitting(true)

    try {
      const user = await registerUser({ name, email, password, role })
      navigate('/registration-submitted', {
        replace: true,
        state: { email: user.email, role: user.role },
      })
    } catch (caughtError) {
      setError(
        caughtError instanceof ApiError
          ? caughtError.message
          : 'Unable to create your account. Please try again.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="auth-card auth-card--register">
      <span className="eyebrow">Request system access</span>
      <h2>Create your account</h2>
      <p className="auth-card__lead">
        Every new account is reviewed before it can sign in.
      </p>

      {error && <Alert tone="error">{error}</Alert>}

      <form className="auth-form" onSubmit={handleSubmit}>
        <FormField
          id="register-name"
          label="Full name"
          type="text"
          autoComplete="name"
          placeholder="Your full name"
          minLength={1}
          maxLength={255}
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
        />
        <FormField
          id="register-email"
          label="Email address"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />

        <fieldset className="role-picker">
          <legend>Account type</legend>
          <label className={role === 'COMMUNITY' ? 'is-selected' : ''}>
            <input
              type="radio"
              name="role"
              value="COMMUNITY"
              checked={role === 'COMMUNITY'}
              onChange={() => setRole('COMMUNITY')}
            />
            <span className="role-picker__icon" aria-hidden="true">C</span>
            <span><strong>Community</strong><small>Local access and updates</small></span>
          </label>
          <label className={role === 'MET_ADMIN' ? 'is-selected' : ''}>
            <input
              type="radio"
              name="role"
              value="MET_ADMIN"
              checked={role === 'MET_ADMIN'}
              onChange={() => setRole('MET_ADMIN')}
            />
            <span className="role-picker__icon" aria-hidden="true">M</span>
            <span><strong>MET admin</strong><small>Requires administrator approval</small></span>
          </label>
        </fieldset>

        <div className="form-grid">
          <FormField
            id="register-password"
            label="Password"
            type="password"
            autoComplete="new-password"
            placeholder="Minimum 8 characters"
            minLength={8}
            maxLength={128}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <FormField
            id="register-password-confirm"
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            placeholder="Repeat password"
            minLength={8}
            maxLength={128}
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
          />
        </div>

        <button className="button button--primary button--full" disabled={isSubmitting}>
          {isSubmitting ? 'Submitting request…' : 'Create account'}
        </button>
      </form>

      <p className="auth-card__switch">
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </div>
  )
}
