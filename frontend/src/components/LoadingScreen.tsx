export function LoadingScreen() {
  return (
    <main
      className="auth-session-loader"
      aria-live="polite"
      aria-busy="true"
      aria-atomic="true"
    >
      <div className="auth-session-loader__content">
        <img
          className="auth-session-loader__logo"
          src="/fijimetlogo.svg"
          alt=""
          aria-hidden="true"
        />

        <div className="auth-session-loader__identity">
          <strong>Fiji Meteorological Service</strong>
          <span>Flood Risk Prediction &amp; Community Alert System</span>
        </div>

        <div className="auth-session-loader__indicator" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>

        <p>Checking session…</p>
      </div>
    </main>
  )
}
