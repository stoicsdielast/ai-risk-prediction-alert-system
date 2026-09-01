/**
 * TopNav - Horizontal navigation bar (persistent across all pages)
 * Layout: Wordmark (left) | 6 nav items (center) | Admin avatar (right)
 */

import React from 'react';
import type { Admin } from '../../types';

interface TopNavProps {
  currentAdmin: Admin;
  currentPage:
    | 'dashboard'
    | 'alerts'
    | 'thresholds'
    | 'locations'
    | 'users'
    | 'reports';
  onNavigate?: (pageId: string) => void;
}

/**
 * NavItem - single navigation item with label
 * Active state when matches currentPage
 */
interface NavItemProps {
  label: string;
  isActive: boolean;
  onClick: () => void;
}

const NavItem: React.FC<NavItemProps> = ({
  label,
  isActive,
  onClick,
}) => (
  <button
    className={`nav-item ${isActive ? 'active' : ''}`}
    onClick={onClick}
    title={label}
  >
    <span className="nav-label">{label}</span>
  </button>
);

/**
 * TopNav component - horizontal persistent navigation
 */
export const TopNav: React.FC<TopNavProps> = ({ currentAdmin, currentPage, onNavigate }) => {
  // Navigation items in exact order per spec
  const navItems = [
    {
      id: 'dashboard',
      label: 'Dashboard',
      href: '/dashboard',
    },
    {
      id: 'alerts',
      label: 'Alert management',
      href: '/alerts',
    },
    {
      id: 'thresholds',
      label: 'Thresholds',
      href: '/thresholds',
    },
    {
      id: 'locations',
      label: 'Locations',
      href: '/locations',
    },
    {
      id: 'users',
      label: 'Users',
      href: '/users',
    },
    {
      id: 'reports',
      label: 'Reports',
      href: '/reports',
    },
  ];

  const handleNavClick = (pageId: string) => {
    if (onNavigate) {
      onNavigate(pageId);
    }
  };

  return (
    <nav className="top-nav">
      {/* Left: Wordmark */}
      <div className="nav-wordmark">
        <span>Fiji MET admin</span>
      </div>

      {/* Center: 6 nav items */}
      <div className="nav-items">
        {navItems.map((item) => (
          <NavItem
            key={item.id}
            label={item.label}
            isActive={currentPage === item.id}
            onClick={() => handleNavClick(item.id)}
          />
        ))}
      </div>

      {/* Right: Admin avatar with initials */}
      <div className="nav-avatar">
        <div className="avatar-circle" title={currentAdmin.name}>
          {currentAdmin.initials}
        </div>
      </div>
    </nav>
  );
};

export default TopNav;
