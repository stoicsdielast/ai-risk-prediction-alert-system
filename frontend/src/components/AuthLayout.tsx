import { Outlet } from 'react-router-dom'
import { Brand } from './Brand'

export function AuthLayout() {
  return (
    <main className="auth-layout">
      <section className="auth-story" aria-label="About FloodWatch Fiji">
        <div className="auth-story__glow auth-story__glow--one" />
        <div className="auth-story__glow auth-story__glow--two" />
        <Brand inverse />

        <div className="auth-story__content">
          <span className="eyebrow eyebrow--light">Community-ready intelligence</span>
          <h1>Safer decisions before the water rises.</h1>
          <p>
            One trusted access point for Fiji MET teams and communities preparing
            for flood risk.
          </p>

          <div className="story-proof">
            <div className="story-proof__icon" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <div>
              <strong>Built for Fiji</strong>
              <small>Secure account review keeps the right people connected.</small>
            </div>
          </div>
        </div>

        <p className="auth-story__footer">
          Flood Risk Prediction &amp; Community Alert System
        </p>
      </section>

      <section className="auth-panel">
        <div className="auth-panel__mobile-brand">
          <Brand />
        </div>
        <div className="auth-panel__content">
          <Outlet />
        </div>
        <p className="auth-panel__footer">A Fiji MET university project</p>
      </section>
    </main>
  )
}
