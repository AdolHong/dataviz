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
