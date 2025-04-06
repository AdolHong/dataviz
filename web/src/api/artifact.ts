import { axiosInstance } from '@/lib/axios';
import type {
  ArtifactRequest,
  ArtifactResponse,
  ArtifactCodeReponse,
} from '@/types/api/aritifactRequest';

export const artifactApi = {
  // 执行可视化
  async executeArtifact(request: ArtifactRequest): Promise<ArtifactResponse> {
    const response = await axiosInstance.post('/execute_artifact', request);
    return response.data;
  },

  // 获取格式化后的Python代码
  async getArtifactCode(
    request: ArtifactRequest
  ): Promise<ArtifactCodeReponse> {
    const response = await axiosInstance.post('/artifact_code', request);
    return response.data;
  },
};
