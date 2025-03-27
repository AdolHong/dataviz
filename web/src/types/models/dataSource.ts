// 数据源接口
export interface DataSource {
  id: string;
  name: string;
  description?: string;
  executor: {
    type: string;
    engine: string;
  };
  code: string;
  updateMode?: {
    type: 'auto' | 'manual';
    interval?: number;
  };
}
