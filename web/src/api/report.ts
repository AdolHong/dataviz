import { axiosInstance } from '@/lib/axios';
import type { Report } from '@/types';

export const reportApi = {
  // 根据文件ID获取报表配置
  async getReportByFileId(fileId: string): Promise<Report> {
    const { data } = await axiosInstance.get(`/report/${fileId}`);
    return data;
  },

  // 更新报表配置
  async updateReport(fileId: string, report: Report): Promise<Report> {
    const { data } = await axiosInstance.post(`/report/${fileId}`, report);
    return data;
  },

  // 获取所有报表列表
  async listReports(): Promise<
    Array<{
      id: string;
      title: string;
      description: string;
      updatedAt: string;
      createdAt: string;
    }>
  > {
    const { data } = await axiosInstance.get('/reports');
    return data;
  },

  // 创建新报表
  async createReport(
    report: Partial<Report>,
    parentId?: string
  ): Promise<Report> {
    const params = parentId ? { parent_id: parentId } : {};
    const { data } = await axiosInstance.post('/reports', report, {
      params,
    });
    return data;
  },
};
