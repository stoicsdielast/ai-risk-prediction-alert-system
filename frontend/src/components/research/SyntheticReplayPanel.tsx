import { Link } from 'react-router-dom'
import { SYNTHETIC_NOTICE } from '../../api/synthetic'

export function SyntheticReplayPanel() {
  return <section className="workspace-banner synthetic-callout" aria-label="Weather analysis" data-source-type="synthetic">
    <div className="workspace-banner__content">
      <div className="workspace-banner__heading">
        <h2>Weather analysis</h2>
        <span className="source-indicator">Synthetic data</span>
      </div>
      <p>Explore historical weather patterns and flood risk predictions across monitored locations.</p>
      <details className="source-details">
        <summary>About this data</summary>
        <p>{SYNTHETIC_NOTICE}. Generated weather and simulator-trained predictions; not live Fiji MET observations or emergency warnings. Alert exercises use a separate simulated workflow.</p>
      </details>
    </div>
    <Link className="button button--primary workspace-banner__action" to="/simulation">Explore historical analysis <span aria-hidden="true">→</span></Link>
  </section>
}
