// 可视化接口
export interface Artifact {
  id: string; // 自动生成
  title: string;
  description?: string;
  code: string;
  dependencies: string[]; // 依赖哪个数据源
  executor_engine: string;
  plainParams?: (SinglePlainParam | MultiplePlainParam)[];
  cascaderParams?: CascaderParam[];
}

export interface SinglePlainParam {
  type: 'single';
  id: string; // 自动生成
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  valueType: 'string' | 'double' | 'boolean' | 'int';
  default: string;
  choices: Record<string, string>[];
}

export interface MultiplePlainParam {
  type: 'multiple';
  id: string; // 自动生成
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  valueType: 'string' | 'double' | 'boolean' | 'int';
  default: string[];
  choices: Record<string, string>[];
}

export interface CascaderParam {
  dfAlias: string;
  levels: CascaderLevel[];
}

export interface CascaderLevel {
  dfColumn: string;
  name?: string;
  description?: string;
}
