interface Alert {
  type: 'info' | 'warning' | 'error';
  message: string;
}

export interface QueryResponseDataContext {
  rowNumber: number;
  demoData: string;
  uniqueId: string;
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

export interface QueryResponse {
  status: string;
  message: string;
  error: string;
  alerts: Alert[];
  data: QueryResponseDataContext;
  codeContext: QueryResponseCodeContext;
  cascaderContext: Record<string, string>;
  queryTime: string;
}
