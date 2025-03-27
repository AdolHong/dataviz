// 数据源接口
export interface DataSource {
  name: string;
  description?: string;
  executor: {
    type: "sql" | "python";
    engine: string;
  };
  code: string;
  updateMode?: {
    type: "auto" | "manual";
    interval?: number;
  };
}
