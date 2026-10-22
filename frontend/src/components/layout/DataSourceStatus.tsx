import { SYNTHETIC_NOTICE } from '../../api/synthetic'

export function DataSourceStatus({ synthetic = false }: { synthetic?: boolean }) {
  return (
    <details className="data-source-status">
      <summary>{synthetic ? 'Synthetic data' : 'Data sources & status'}</summary>
      <div className="data-source-status__content">
        <strong>Data sources & status</strong>
        <dl>
          <div>
            <dt>Weather records</dt>
            <dd>The map and historical analysis currently use generated historical weather, not live Fiji MET station observations.</dd>
          </div>
          <div>
            <dt>Flood risk predictions</dt>
            <dd>Model estimates support review. Sample records are labelled; synthetic model results do not establish real forecast skill.</dd>
          </div>
          <div>
            <dt>Community alerts</dt>
            <dd>Published alerts are administrator approved. Simulated alerts are labelled and are not emergency warnings. Official Fiji MET warnings are issued separately and take precedence.</dd>
          </div>
          <div data-source-type="synthetic">
            <dt>{SYNTHETIC_NOTICE}</dt>
            <dd>Historical analysis and scenario analysis use synthetic data. Their simulated alert workflows are separate from operational alerts.</dd>
          </div>
        </dl>
      </div>
    </details>
  )
}
