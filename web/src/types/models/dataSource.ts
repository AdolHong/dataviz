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
  alias: string; // 别名, 比如df_sales
  description?: string;
  executor:
    | PythonSourceExecutor
    | SQLSourceExecutor
    | CSVSourceExecutor
    | CSVUploaderSourceExecutor;
}

// 处理更新模式变更
export const handleUpdateModeChange =
  (dataSource: DataSource, type: 'manual' | 'auto') =>
  (newDataSource: DataSource) => {
    newDataSource = {
      ...dataSource,
      executor: {
        ...(dataSource.executor as PythonSourceExecutor | SQLSourceExecutor),
        updateMode: {
          type,
          ...(type === 'auto' ? { interval: 600 } : {}),
        },
      },
    };

    return newDataSource;
  };
export const handleEngineChange =
  (dataSource: DataSource, engine: string) => (newDataSource: DataSource) => {
    console.info(dataSource.executor);

    newDataSource = {
      ...dataSource,
      executor: {
        ...(dataSource.executor as PythonSourceExecutor | SQLSourceExecutor),
        engine,
      },
    };
    return newDataSource;
  };

// 处理执行器类型变更
export const handleExecutorTypeChange =
  (
    dataSource: DataSource,
    type: 'python' | 'sql' | 'csv_data' | 'csv_uploader'
  ) =>
  (newDataSource: DataSource) => {
    newDataSource = { ...dataSource };

    switch (type) {
      case 'python':
        newDataSource.executor = {
          type: 'python',
          engine: 'default',
          code: '',
          updateMode: { type: 'manual' },
        };
        break;
      case 'sql':
        newDataSource.executor = {
          type: 'sql',
          engine: 'default',
          code: '',
          updateMode: { type: 'manual' },
        };
        break;
      case 'csv_data':
        newDataSource.executor = {
          type: 'csv_data',
          data: '',
        };
        break;
      case 'csv_uploader':
        newDataSource.executor = {
          type: 'csv_uploader',
          demoData: '',
        };
        break;
    }
    return newDataSource;
  };
