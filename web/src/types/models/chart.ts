// 可视化接口
export interface Chart {
  id: string; // 自动生成
  title: string;
  description?: string;
  code: string;
  dependencies: string[]; // 依赖哪个数据源
  executor_engine: string;
  chartParams?: ChartParam[];
}

// 可视化参数接口
export interface ChartParam {
  id: string; // 自动生成
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  valueType: 'string' | 'double' | 'boolean' | 'int';
  paramType:
    | PlainSingleChartParamType
    | PlainMultipleChartParamType
    | CascadeSingleChartParamType
    | CascadeMultipleChartParamType;
}

export interface PlainSingleChartParamType {
  type: 'plain_single';
  default: string;
  choices: string[];
}

export interface PlainMultipleChartParamType {
  type: 'plain_multiple';
  default: string[];
  choices: string[];
  dfAlias: string;
  dfColumn: string;
}

export interface CascadeSingleChartParamType {
  type: 'cascade_single';
  default: string;
  choices: string[];
  dfAlias: string;
  dfColumn: string;
  level: number;
}

export interface CascadeMultipleChartParamType {
  type: 'cascade_multiple';
  default: string[];
  choices: string[];
  dfAlias: string;
  dfColumn: string;
  level: number;
}
