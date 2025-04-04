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
