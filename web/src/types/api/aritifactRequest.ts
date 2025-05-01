import type { Alert } from './queryResponse';

export interface ArtifactRequest {
  uniqueId: string;
  dfAliasUniqueIds: Record<string, string>;
  plainParamValues: Record<string, PlainParamValue>;
  cascaderParamValues: Record<string, string[] | string[][]>;
  inferredParamValues?: Record<string, string | string[]>;
  pyCode: string;
  engine: string;
}

export interface PlainParamValue {
  name: string;
  type: 'single' | 'multiple';
  valueType: 'string' | 'double' | 'boolean' | 'int';
  value: string | string[];
}

export interface ArtifactCodeContext {
  uniqueId: string;
  dfAliasUniqueIds: Record<string, string>;
  plainParamValues: Record<string, PlainParamValue>;
  cascaderParamValues: Record<string, string[] | string[][]>;
  inferredParamValues?: Record<string, string | string[]>;
  pyCode: string;
  engine: string;
}

export interface ArtifactTextDataContext {
  type: 'text';
  data: string;
}

export interface ArtifactImageDataContext {
  type: 'image';
  data: string;
}

export interface ArtifactTableDataContext {
  type: 'table';
  data: string;
}

export interface ArtifactPlotlyDataContext {
  type: 'plotly';
  data: string;
}

export interface ArtifactEChartDataContext {
  type: 'echart';
  data: string;
}

export interface ArtifactAltairDataContext {
  type: 'altair';
  data: string;
}

export interface ArtifactResponse {
  status: string;
  message: string;
  error: string;
  alerts: Alert[];
  codeContext: ArtifactCodeContext;
  queryTime: string;
  dataContext:
    | ArtifactTextDataContext
    | ArtifactImageDataContext
    | ArtifactTableDataContext
    | ArtifactPlotlyDataContext
    | ArtifactEChartDataContext
    | ArtifactAltairDataContext;
}

export interface ArtifactCodeReponse {
  status: string;
  message: string;
  error: string;
  alerts: Alert[];
  pyCode: string;
  queryTime: string;
}
