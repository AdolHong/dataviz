import { axiosInstance } from '@/lib/axios';
import type { Report } from '@/types';

export interface QueryBySourceRequest {
  fileId: string;
  sourceId: string;
  updateTime: string;
  paramValues: Record<string, any>;
  code: string;
  data_content?: string;
}

export interface QueryResponse {
  status: string;
  message: string;
  error?: string;
}

export const queryApi = {
  // 根据数据源ID执行查询
  async queryBySourceId(request: QueryBySourceRequest): Promise<QueryResponse> {
    const response = await axiosInstance.post('/query_by_source_id', request);

    console.log(response.data);

    return response.data;
  },

  // 执行SQL查询并缓存结果
  async executeQueryBySourceId(
    fileId: string,
    sourceId: string,
    updateTime: string,
    paramValues: Record<string, any> = {},
    code: string,
    dataContent: string = ''
  ): Promise<any> {
    const { data } = await axiosInstance.post('/query_by_source_id', {
      fileId: fileId,
      sourceId: sourceId,
      updateTime: updateTime,
      paramValues: paramValues,
      code: code,
      dataContent: dataContent,
    });
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
