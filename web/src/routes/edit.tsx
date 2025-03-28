import { createFileRoute } from '@tanstack/react-router';
import { useState, useEffect } from 'react';
import EditModal from '@/pages/edit/EditModal';

import { reportApi } from '@/api/report';
import type { ReportResponse } from '@/types'; // Use type-only import
import { toast } from 'sonner';

import { useStore } from '@/lib/store';

export const Route = createFileRoute('/edit')({
  component: EditPage,
});

function EditPage() {
  const [config, setConfig] = useState<any>(null);
  const { dashboardId } = useStore();
  const [isModalOpen, setIsModalOpen] = useState(true);

  useEffect(() => {
    async function fetchDashboardConfig() {
      toast.success('获取仪表板配置成功1');
      toast.success('获取仪表板配置成功2');
      toast.success('获取仪表板配置成功3');

      if (!dashboardId) return;

      try {
        const response = await reportApi.getReportConfig(dashboardId);
        setConfig(response);
      } catch (error) {
        console.error('获取仪表板配置失败:', error);
      }
    }

    fetchDashboardConfig();
  }, [dashboardId]);

  const handleSave = async (
    parameters: any[],
    visualizations: any[],
    sqlCode: string
  ) => {
    if (!config) return;

    try {
      const updatedConfig: ReportResponse = {
        ...config,
        parameters,
        visualization: visualizations,
        query: {
          ...config.query,
          code: sqlCode,
        },
      };

      await reportApi.updateReportConfig(updatedConfig);

      // 更新本地状态
      useStore.setState({
        dashboardParameters: parameters,
        dashboardVisualizations: visualizations,
        dashboardSqlCode: sqlCode,
      });

      // 重定向回仪表板页面
      window.history.back();
    } catch (error) {
      console.error('保存配置失败:', error);
    }
  };

  return (
    <div>
      <EditModal
        open={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        reportId={'临时id'} // todo: 获取报表的id
      />
    </div>
  );
}
