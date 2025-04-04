export interface QueryRequest {
  uniqueId: string;
  fileId: string;
  sourceId: string;
  reportUpdateTime: string;
  requestContext:
    | QueryBySQLRequestContext
    | QueryByPythonRequestContext
    | QueryByCsvDataRequestContext
    | QueryByCsvUploadRequestContext;
  cascaderContext?: string[];
}

export interface QueryBySQLRequestContext {
  type: 'sql';
  engine: string;
  code: string;
  parsedCode: string;
  paramValues?: { [key: string]: any };
}

export interface QueryByPythonRequestContext {
  type: 'python';
  engine: string;
  code: string;
  parsedCode: string;
  paramValues?: { [key: string]: any };
}

export interface QueryByCsvDataRequestContext {
  type: 'csv_data';
}

export interface QueryByCsvUploadRequestContext {
  type: 'csv_uploader';
  dataContent: string;
}

export interface QueryResponse {
  status: string;
  message: string;
  error: string;
  alerts: Alert[];
  data: QueryResponseDataContext;
  codeContext: QueryResponseCodeContext;
}

export interface QueryResponseDataContext {
  rowNumber: number;
  demoData: string;
  uniqueId: string;
  cascaderContext: Record<string, string>;
}
export interface QueryResponseCodeContext {
  fileId: string;
  sourceId: string;
  type: 'sql' | 'python' | 'csv_data' | 'csv_uploader';
  engine?: string;
  code?: string;
  parsedCode?: string;
  paramValues?: { [key: string]: any };
}

interface Alert {
  type: 'info' | 'warning' | 'error';
  message: string;
}
