export interface SingleSelectParamConfig {
  type: 'single_select';
  choices: string[];
  default: string;
}

export interface MultiSelectParamConfig {
  type: 'multi_select';
  choices: string[];
  default: string[];
  sep: string;
  wrapper: string;
}

export interface DatePickerParamConfig {
  type: 'date_picker';
  dateFormat: string;
  default: string;
}

export interface MultiInputParamConfig {
  type: 'multi_input';
  default: string[];
  sep: string;
  wrapper: string;
}

export interface SingleInputParamConfig {
  type: 'single_input';
  default: string;
}

// 参数接口
export type Parameter = {
  id: string; // 自动生成
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  paramConfig:
    | SingleSelectParamConfig
    | MultiSelectParamConfig
    | DatePickerParamConfig
    | MultiInputParamConfig
    | SingleInputParamConfig;
};

export type SingleSelectParamConfig = { ... };
export type MultiSelectParamConfig = { ... };
// 其他类型定义
