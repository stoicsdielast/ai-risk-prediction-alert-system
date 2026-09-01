/**
 * MetricsRow - 4 metric cards in a single row
 * Displays: Pending alerts, Active alerts, Monitored locations, Pending users
 * REQ-32: view key metrics
 */

import React from 'react';
import type { Metrics } from '../../types';
import MetricCard from './MetricCard';

interface MetricsRowProps {
  metrics: Metrics;
}

/**
 * MetricsRow component - 4-column grid of metric cards
 */
export const MetricsRow: React.FC<MetricsRowProps> = ({ metrics }) => (
  <div className="metrics-row">
    <MetricCard label="Pending alerts" value={metrics.pending_alerts} />
    <MetricCard label="Active alerts" value={metrics.active_alerts} />
    <MetricCard
      label="Monitored locations"
      value={metrics.monitored_locations}
    />
    <MetricCard label="Pending users" value={metrics.pending_users} />
  </div>
);

export default MetricsRow;
