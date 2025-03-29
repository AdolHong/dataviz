export interface SingleSelectParamConfig {
  Config: 'single_select';
  choices: string[];
  default: string;
}

export interface MultiSelectParamConfig {
  Config: 'multi_select';
  choices: string[];
  default: string[];
  sep: string;
  wrapper: string;
}

export interface DatePickerParamConfig {
  Config: 'date_picker';
  dateFormat: string;
  default: string;
}

export interface MultiInputParamConfig {
  Config: 'multi_input';
  default: string[];
  sep: string;
  wrapper: string;
}

export interface SingleInputParamConfig {
  Config: 'single_input';
  default: string;
}

// 参数接口
export interface Parameter {
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
}
