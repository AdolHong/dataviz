export type { ReportResponse } from './api/reportResponse';

export * from './models/artifact';

export * from './models/datasource';

export type { Parameter } from './models/parameter';

export type { Report } from './models/report';

export type { Layout, LayoutItem } from './models/layout';

export type { EngineChoices } from './models/engineChoices';

export interface DataSource {
  id: string;
  name: string;
  alias: string;
  executor: {
    type: string;
    engine?: string;
    code?: string;
    updateMode?: { type: string };
    demoData?: string;
    [key: string]: any;
  };
}

export interface ReportResponse {
  id: string;
  title: string;
  description: string;
  dataSources: DataSource[];
  parameters: Parameter[];
  artifacts: any[];
  layout: Layout;
}
