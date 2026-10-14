import { Link } from 'react-router-dom'

function PredictionIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 18V9m5 9V5m6 13v-7m5 7V3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="m3 7 5-4 6 5 6-5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function MapIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m3 6 5-3 8 3 5-3v15l-5 3-8-3-5 3V6Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8 3v15m8-12v15"
        stroke="currentColor"
        strokeWidth="1.8"
      />
    </svg>
  )
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function WelcomePage() {
  return (
    <main className="landing-page" id="top">
      <header className="landing-header">
        <div className="landing-header__inner">
          <Link className="landing-brand" to="/" aria-label="Fiji Meteorological Service home">
            <img
              className="landing-brand__logo"
              src="/fijimetlogo.svg"
              alt=""
              aria-hidden="true"
            />
            <span className="landing-brand__copy">
              <strong>Fiji Meteorological Service</strong>
              <small>Flood Risk Prediction &amp; Community Alert System</small>
            </span>
          </Link>

          <nav className="landing-nav" aria-label="Main navigation">
            <a className="landing-nav__link" href="#top" aria-current="page">
              Home
            </a>
            <Link className="landing-nav__link" to="/weather-map">
              Weather Map
            </Link>
            <a className="landing-nav__link" href="#alerts">
              Alerts
            </a>
            <Link className="landing-nav__signin" to="/login">
              Sign In
            </Link>
          </nav>
        </div>
      </header>

      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero__inner">
          <div className="landing-hero__copy">
            <span className="landing-pill">AI-powered flood early warning</span>
            <h1 id="landing-title">
              Flood Risk Information
              <span>When It Matters Most</span>
            </h1>
            <p>
              Monitor flood-risk predictions, weather conditions and community
              alerts for supported locations across Fiji.
            </p>

            <div className="landing-hero__actions">
              <Link className="landing-button landing-button--primary" to="/weather-map">
                View Flood Risk Map
                <span aria-hidden="true">→</span>
              </Link>
              <Link className="landing-button landing-button--secondary" to="/login">
                Sign In
              </Link>
            </div>

            <ul className="landing-trust-pills" aria-label="System highlights">
              <li>AI powered</li>
              <li>Fiji MET</li>
              <li>Flood alerts</li>
            </ul>
          </div>

          <aside className="landing-preview" aria-label="Flood intelligence workflow preview">
            <header className="landing-preview__header">
              <div>
                <span>Operational workflow</span>
                <strong>From observation to alert</strong>
              </div>
              <span className="landing-preview__badge">Prototype</span>
            </header>

            <ol className="landing-preview__steps">
              <li className="landing-preview__step">
                <span className="landing-preview__number">01</span>
                <div>
                  <strong>Monitor conditions</strong>
                  <small>Review supported weather locations</small>
                </div>
                <span className="landing-preview__state">Observe</span>
              </li>
              <li className="landing-preview__step">
                <span className="landing-preview__number">02</span>
                <div>
                  <strong>Assess flood risk</strong>
                  <small>Compare AI guidance with official information</small>
                </div>
                <span className="landing-preview__state">Assess</span>
              </li>
              <li className="landing-preview__step">
                <span className="landing-preview__number">03</span>
                <div>
                  <strong>Inform communities</strong>
                  <small>Share reviewed flood-risk warnings</small>
                </div>
                <span className="landing-preview__state">Inform</span>
              </li>
            </ol>

            <footer className="landing-preview__footer">
              <span className="landing-preview__pulse" aria-hidden="true" />
              Decision support for supported locations across Fiji
            </footer>
          </aside>
        </div>
      </section>

      <section className="landing-features" id="alerts" aria-labelledby="features-title">
        <div className="landing-features__inner">
          <header className="landing-features__heading">
            <span>One connected service</span>
            <h2 id="features-title">Understand risk. See conditions. Stay informed.</h2>
            <p>
              A focused set of tools designed to support faster, clearer flood-risk
              decisions for Fiji.
            </p>
          </header>

          <div className="landing-feature-grid">
            <article className="landing-feature-card">
              <div className="landing-feature-card__icon">
                <PredictionIcon />
              </div>
              <span className="landing-feature-card__pill">AI powered</span>
              <h3>Flood Risk Predictions</h3>
              <p>AI-assisted flood-risk information for monitored areas.</p>
            </article>

            <article className="landing-feature-card">
              <div className="landing-feature-card__icon">
                <MapIcon />
              </div>
              <span className="landing-feature-card__pill">Map view</span>
              <h3>Interactive Weather Map</h3>
              <p>View supported locations and their current flood-risk status.</p>
              <Link className="landing-feature-card__link" to="/weather-map">
                Explore the map <span aria-hidden="true">→</span>
              </Link>
            </article>

            <article className="landing-feature-card">
              <div className="landing-feature-card__icon">
                <AlertIcon />
              </div>
              <span className="landing-feature-card__pill">Flood alerts</span>
              <h3>Community Alerts</h3>
              <p>Stay informed about approved flood-risk warnings.</p>
              <Link className="landing-feature-card__link" to="/alerts">
                View community alerts <span aria-hidden="true">→</span>
              </Link>
            </article>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="landing-footer__inner">
          <div className="landing-footer__brand">
            <img src="/fijimetlogo.svg" alt="" aria-hidden="true" />
            <span>
              <strong>Fiji Meteorological Service</strong>
              <small>Flood-risk decision support for Fiji</small>
            </span>
          </div>
          <p>University prototype · Weather and alert information is for demonstration.</p>
        </div>
      </footer>
    </main>
  )
}
