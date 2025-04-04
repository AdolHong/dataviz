import type { Alert } from './queryResponse';

export interface ArtifactRequest {
  uniqueId: string;
  dfAliasUniqueIds: Record<string, string>;
  plainParamValues: Record<string, string | string[]>;
  cascaderParamValues: Record<string, string | string[]>;
  pyCode: string;
  engine: string;
}

export interface ArtifactCodeContext {
  uniqueId: string;
  dfAliasUniqueIds: Record<string, string>;
  plainParamValues: Record<string, string | string[]>;
  cascaderParamValues: Record<string, string | string[]>;
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
  dataContext:
    | ArtifactTextDataContext
    | ArtifactImageDataContext
    | ArtifactTableDataContext
    | ArtifactPlotlyDataContext
    | ArtifactEChartDataContext
    | ArtifactAltairDataContext;
}
