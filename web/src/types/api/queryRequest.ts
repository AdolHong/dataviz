export interface QueryBySQLRequestContext {
  type: 'sql';
  fileId: string;
  sourceId: string;
  reportUpdateTime: string;
  engine: string;
  code: string;
  parsedCode: string;
  paramValues?: { [key: string]: any };
}

export interface QueryByPythonRequestContext {
  type: 'python';
  fileId: string;
  sourceId: string;
  reportUpdateTime: string;
  engine: string;
  code: string;
  parsedCode: string;
  paramValues?: { [key: string]: any };
}

export interface QueryByCsvDataRequestContext {
  type: 'csv_data';
  fileId: string;
  sourceId: string;
  reportUpdateTime: string;
}

export interface QueryByCsvUploadRequestContext {
  type: 'csv_uploader';
  fileId: string;
  sourceId: string;
  reportUpdateTime: string;
  dataContent: string;
}
export interface CascaderContext {
  required: string[];
  inferred?: { [key: string]: string };
}

export interface InferredContext {
  required: string[];
  inferred?: { [key: string]: string[] };
}

export interface QueryRequest {
  uniqueId: string;

  requestContext:
    | QueryBySQLRequestContext
    | QueryByPythonRequestContext
    | QueryByCsvDataRequestContext
    | QueryByCsvUploadRequestContext;
  cascaderContext?: CascaderContext;
  inferredContext?: InferredContext;
}
