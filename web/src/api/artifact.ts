import { axiosInstance } from '@/lib/axios';
import type {
  ArtifactRequest,
  ArtifactResponse,
} from '@/types/api/aritifactRequest';

export const artifactApi = {
  // 执行可视化
  async executeArtifact(request: ArtifactRequest): Promise<ArtifactResponse> {
    const response = await axiosInstance.post('/execute_artifact', request);
    return response.data;
  },
};
