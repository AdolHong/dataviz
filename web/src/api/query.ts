import { axiosInstance } from '@/lib/axios';
import type { QueryRequest } from '@/types/api/queryRequest';
import type { QueryResponse } from '@/types/api/queryResponse';

export const queryApi = {
  // 执行查询
  async executeQueryBySourceId(request: QueryRequest): Promise<QueryResponse> {
    const response = await axiosInstance.post('/query_by_source_id', request);
    return response.data;
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
