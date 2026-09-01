import { useMemo, useState } from 'react';
import Dashboard from './components/Dashboard/Dashboard';
import AlertManagement from './components/Dashboard/AlertManagement';
import type { Admin } from './types';

/**
 * Main App component
 * TODO: Once authentication is implemented, fetch currentAdmin from auth context or session
 * For now, using a mock admin for demo purposes
 */
function App() {
  // Mock admin - TODO: replace with authenticated user from auth state
  const currentAdmin: Admin = useMemo(
    () => ({
      id: '550e8400-e29b-41d4-a716-446655440000',
      name: 'Aryan S.',
      email: 'aryan@fiji-met.gov.fj',
      initials: 'AS',
      role: 'admin',
    }),
    []
  );

  // Page routing state
  const [currentPage, setCurrentPage] = useState<string>('dashboard');

  // Handle navigation from TopNav
  const handleNavigation = (pageId: string) => {
    setCurrentPage(pageId);
    window.scrollTo(0, 0);
  };

  return (
    <div>
      {currentPage === 'dashboard' && (
        <Dashboard currentAdmin={currentAdmin} onNavigate={handleNavigation} />
      )}
      {currentPage === 'alerts' && (
        <AlertManagement currentAdmin={currentAdmin} onNavigate={handleNavigation} />
      )}
    </div>
  );
}

export default App;
