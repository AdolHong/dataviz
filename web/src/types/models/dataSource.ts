export interface ManualUpdateMode {
  type: 'manual';
}

export interface AutoUpdateMode {
  type: 'auto';
  interval?: number;
}

export interface PythonSourceExecutor {
  type: 'python';
  engine: string;
  // imports?: string;
  code: string;
  updateMode: ManualUpdateMode | AutoUpdateMode;
}

export interface SQLSourceExecutor {
  type: 'sql';
  engine: string;
  code: string;
  updateMode: ManualUpdateMode | AutoUpdateMode;
}

export interface CSVSourceExecutor {
  type: 'csv_data';
  data: string;
}

export interface CSVUploaderSourceExecutor {
  type: 'csv_uploader';
  demoData: string;
}

// 数据源接口
export interface DataSource {
  id: string; // 自动生成
  name: string; // 中英文均可
  description?: string;
  executor:
    | PythonSourceExecutor
    | SQLSourceExecutor
    | CSVSourceExecutor
    | CSVUploaderSourceExecutor;
}
