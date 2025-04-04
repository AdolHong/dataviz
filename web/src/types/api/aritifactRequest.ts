import type { Alert } from './queryResponse';

export interface ArtifactRequest {
  uniqueId: string;
  dfAliasUniqueIds: Record<string, string>;
  plainParamValues: Record<string, string | string[]>;
  cascaderParamValues: Record<string, string | string[]>;
  pyCode: string;
  engine: string;
}

export interface ArtifactResponse {
  status: string;
  message: string;
  error: string;
  alerts: Alert[];
  codeContext: {
    uniqueId: string;
    dfAliasUniqueIds: Record<string, string>;
    plainParamValues: Record<string, string | string[]>;
    cascaderParamValues: Record<string, string | string[]>;
    pyCode: string;
    engine: string;
  };
  dataContext: null;
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

export interface ArtifactTablePlotlyContext {
  type: 'plotly';
  data: string;
}

export interface ArtifactTableEChartContext {
  type: 'echart';
  data: string;
}

export interface ArtifactTableAltairContext {
  type: 'altair';
  data: string;
}
