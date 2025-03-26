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

// 参数接口
export interface Parameter {
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  type:
    | "single_select"
    | "multi_select"
    | "single_input"
    | "multi_input"
    | "date_picker";
  default?: string;
  choices?: string[];
  format?: {
    dateFormat?: string;
    timeFormat?: string;
    datetimeFormat?: string;
    sep?: string;
    wrapper?: string;
  };
}

// 可视化参数接口
export interface ChartParam {
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  type: "str" | "int" | "float" | "bool";
  selectionMode: "single" | "multiple";
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
  title: string;
  description?: string;
  code: string;
  dependencies: string[]; // 依赖哪个数据源
  executor: {
    type: "python";
    engine: string;
  };
  chartParams?: ChartParam[];
}

// 主要响应接口
export interface Report {
  title: string;
  description?: string;
  dataSources: DataSource[];
  parameters: Parameter[]; // 使用之前定义的 Parameter 接口
  charts: Chart[];
}

export interface ReportResponse extends Report {}
