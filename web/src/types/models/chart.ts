// 可视化参数接口
export interface ChartParam {
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  type: string;
  selectionMode: string;
  default?: string | number | boolean | string[] | number[];
  choices?: string[] | number[];
  // 级联配置
  cascade?: {
    column: string;
    level: number;
  };
}

// 可视化接口
export interface Chart {
  id: string;
  title: string;
  description?: string;
  code: string;
  dependencies: string[]; // 依赖哪个数据源
  executor: {
    type: string;
    engine: string;
  };
  chartParams?: ChartParam[];
}
