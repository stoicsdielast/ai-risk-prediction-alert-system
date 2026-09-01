/**
 * QuickLinksCard - 3 navigation links to other admin pages
 * Links: Thresholds, Locations, Reports
 * Do not add extra links beyond these three
 */

import React from 'react';

/**
 * QuickLinksCard component - provides quick navigation to key admin pages
 */
export const QuickLinksCard: React.FC = () => {
  const handleNavigation = (path: string) => {
    // TODO: implement navigation (react-router or similar)
    console.log('Navigate to:', path);
  };

  return (
    <div className="quick-links-card card">
      <div className="card-header">
        <h3>Quick links</h3>
      </div>

      <div className="card-body">
        <ul className="quick-links-list">
          <li>
            <button
              className="quick-link-btn"
              onClick={() => handleNavigation('/thresholds')}
              title="Configure risk thresholds"
            >
              Configure risk thresholds
            </button>
          </li>
          <li>
            <button
              className="quick-link-btn"
              onClick={() => handleNavigation('/locations')}
              title="Manage monitored locations"
            >
              Manage monitored locations
            </button>
          </li>
          <li>
            <button
              className="quick-link-btn"
              onClick={() => handleNavigation('/reports')}
              title="Generate report"
            >
              Generate report
            </button>
          </li>
        </ul>
      </div>
    </div>
  );
};

export default QuickLinksCard;
