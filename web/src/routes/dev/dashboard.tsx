import { createFileRoute } from '@tanstack/react-router';
import { DashboardPage } from '@/components/dashboard/dashboardPage';

export const Route = createFileRoute('/dev/dashboard')({
  component: Dashboard,
});

function Dashboard() {
  return <DashboardPage />;
}
