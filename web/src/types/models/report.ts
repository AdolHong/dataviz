import type { DataSource } from './dataSource';
import type { Parameter } from './parameter';
import type { Chart } from './chart';
import type { Layout } from './layout';

// 主要响应接口
export interface Report {
  id: string; // 自动生成
  title: string;
  description?: string;
  dataSources: DataSource[];
  parameters: Parameter[]; // 使用之前定义的 Parameter 接口
  charts: Chart[];
  layout: Layout;
}
