import { createFileRoute, redirect } from '@tanstack/react-router';
import { DashboardPage } from '@/components/dashboard/dashboardPage';
import { useSessionIdStore } from '@/lib/store/useSessionIdStore';

export const Route = createFileRoute('/')({
  component: DashboardRoute,
  beforeLoad: async () => {
    // 检查本地存储是否有token
    const token = sessionStorage.getItem('auth-token');
    if (!token) {
      // 如果没有token，重定向到登录页面
      throw redirect({
        to: '/login',
      });
    }
    return { token };
  },
});

function DashboardRoute() {
  return <DashboardPage />;
}
