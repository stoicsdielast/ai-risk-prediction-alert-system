/**
 * MET Admin Dashboard
 * Implements SRS 4.8.1 (View key metrics) and 4.4.1/4.4.2 (Alert management)
 *
 * Layout (top to bottom):
 * 1. TopNav (horizontal, persistent)
 * 2. Page header (title + subtitle)
 * 3. MetricsRow (4 cards in single row)
 * 4. PendingApprovalsPanel (alert list with edit/suppress/approve actions)
 * 5. BottomRow (2 columns: RecentActivity + QuickLinks)
 */

import React, { useEffect, useState } from 'react';
import type { Alert, Admin, Metrics, AuditLogEntry } from '../../types';
import {
  fetchPendingAlerts,
  fetchMetrics,
  fetchRecentActivity,
} from '../../services/alertService';
import TopNav from './TopNav';
import MetricsRow from './MetricsRow';
import PendingApprovalsPanel from './PendingApprovalsPanel';
import RecentActivityCard from './RecentActivityCard';
import QuickLinksCard from './QuickLinksCard';
import './Dashboard.css';

interface DashboardProps {
  currentAdmin: Admin;
  onNavigate?: (pageId: string) => void;
}

/**
 * Dashboard component - main page for admin alert management
 * Assumes currentAdmin is provided via prop (authenticated, from Postgres)
 * All state-changing actions (approve/suppress/edit) are routed through typed API service
 */
export const Dashboard: React.FC<DashboardProps> = ({ currentAdmin, onNavigate }) => {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [recentActivity, setRecentActivity] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * Load dashboard data on mount and after any state-changing action
   */
  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [alertsData, metricsData, activityData] = await Promise.all([
        fetchPendingAlerts(),
        fetchMetrics(),
        fetchRecentActivity(10),
      ]);
      setAlerts(alertsData);
      setMetrics(metricsData);
      setRecentActivity(activityData);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load dashboard data';
      setError(message);
      console.error('Dashboard load error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Load data on mount
  useEffect(() => {
    loadDashboardData();
  }, []);

  /**
   * Callback when alert is approved/suppressed/edited
   * Refreshes alerts list and recent activity
   */
  const handleAlertActionCompleted = async () => {
    await loadDashboardData();
  };

  if (loading) {
    return (
      <div className="dashboard">
        <TopNav currentAdmin={currentAdmin} currentPage="dashboard" onNavigate={onNavigate} />
        <div className="dashboard-content">
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <TopNav currentAdmin={currentAdmin} currentPage="dashboard" onNavigate={onNavigate} />

      <div className="dashboard-content">
        {/* Page Header */}
        <div className="page-header">
          <h1>Admin dashboard</h1>
          <p className="page-subtitle">4.8.1 View key metrics</p>
        </div>

        {/* Error Display */}
        {error && (
          <div className="error-banner">
            <p>{error}</p>
          </div>
        )}

        {/* Metrics Row (4 cards) */}
        {metrics && <MetricsRow metrics={metrics} />}

        {/* Pending Approvals Panel */}
        <PendingApprovalsPanel
          alerts={alerts}
          currentAdmin={currentAdmin}
          onActionCompleted={handleAlertActionCompleted}
        />

        {/* Bottom Row (2 columns) */}
        <div className="bottom-row">
          <RecentActivityCard activity={recentActivity} />
          <QuickLinksCard />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
