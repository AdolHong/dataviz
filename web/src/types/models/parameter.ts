// 参数接口
export interface Parameter {
  id: string; // 自动生成
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  config:
    | SingleSelectParamConfig
    | MultiSelectParamConfig
    | DatePickerParamConfig
    | MultiInputParamConfig
    | SingleInputParamConfig
    | DateRangePickerParamConfig;
}

export interface SingleSelectParamConfig {
  type: 'single_select';
  choices: Record<string, string>[];
  default: string;
}

export interface MultiSelectParamConfig {
  type: 'multi_select';
  choices: Record<string, string>[];
  default: string[];
  sep: string;
  wrapper: string;
}

export interface DatePickerParamConfig {
  type: 'date_picker';
  dateFormat: string;
  default: string;
}

export interface DateRangePickerParamConfig {
  type: 'date_range_picker';
  dateFormat: string;
  default: string[];
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
