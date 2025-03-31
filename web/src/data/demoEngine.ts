import type { EngineChoices } from '@/types/models/engineChoices';

export const demoDataSourceEngineChoices: EngineChoices = {
  sql: ['default', 'starrocks'],
  python: ['default', '3.9'],
};

export const demoArtifactEngineChoices: string[] = ['default'];
