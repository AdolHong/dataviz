import { axiosInstance } from '@/lib/axios';
import type { Report } from '@/types';

export interface QueryBySourceRequest {
  fileId: string;
  sourceId: string;
  updateTime: string;
  uniqueId: string;
  paramValues: Record<string, any> | null;
  code: string | null;
  dataContent: string | null;
}

export interface QueryResponse {
  status: string;
  message: string;
  error?: string;
}

export const queryApi = {
  // 执行查询
  async executeQueryBySourceId(request: QueryBySourceRequest): Promise<any> {
    const { data } = await axiosInstance.post('/query_by_source_id', request);
    return data;
  },

  // 根据查询哈希获取缓存的查询结果
  async getQueryResultByHash(
    queryHash: string,
    sessionId: string
  ): Promise<any> {
    const { data } = await axiosInstance.get(`/query_result/${queryHash}`, {
      params: { session_id: sessionId },
    });
    return data;
  },
};
