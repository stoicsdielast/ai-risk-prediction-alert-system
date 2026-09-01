/**
 * MetricCard - single card showing label + large number
 * Used in MetricsRow (4 cards in one row)
 * REQ-32: view key metrics
 */

import React from 'react';

interface MetricCardProps {
  label: string;
  value: number;
}

/**
 * MetricCard component - displays metric label and value
 * Flat design: white bg, thin border, no shadow
 */
export const MetricCard: React.FC<MetricCardProps> = ({ label, value }) => (
  <div className="metric-card">
    <div className="metric-label">{label}</div>
    <div className="metric-value">{value}</div>
  </div>
);

export default MetricCard;
