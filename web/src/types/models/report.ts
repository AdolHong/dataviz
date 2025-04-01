import type { DataSource } from './dataSource';
import type { Parameter } from './parameter';
import type { Artifact } from './artifact';
import type { Layout } from './layout';
import {
  type AliasRelianceMap,
  createAliasRelianceMap,
  upsertAliasRelianceMapByDataSource,
} from './aliasRelianceMap';

// 主要响应接口
export interface Report {
  id: string; // 自动生成
  title: string;
  description?: string;
  dataSources: DataSource[];
  parameters: Parameter[]; // 使用之前定义的 Parameter 接口
  artifacts: Artifact[];
  layout: Layout;
  createdAt: string;
  updatedAt: string;
}

// 添加数据源
export const addDataSource = (
  source: DataSource,
  dataSources: DataSource[],
  aliasRelianceMap: AliasRelianceMap
): { newDataSources: DataSource[]; newAliasRelianceMap: AliasRelianceMap } => {
  const length = dataSources.length;
  const newSource = {
    ...source,
    id: `source_${length + 1}`,
  };

  // 更新aliasRelianceMap: source与artifacts的依赖关系
  const newAliasRelianceMap = upsertAliasRelianceMapByDataSource(
    null,
    newSource,
    aliasRelianceMap
  );

  // 更新dataSources
  const newDataSources = [...dataSources, newSource];

  return {
    newDataSources,
    newAliasRelianceMap,
  };
};

// 编辑数据源
export const editDataSource = (
  oldSource: DataSource,
  newSource: DataSource,
  dataSources: DataSource[],
  aliasRelianceMap: AliasRelianceMap
): { newDataSources: DataSource[]; newAliasRelianceMap: AliasRelianceMap } => {
  const newDataSources = dataSources.map((item) => {
    return item.id === newSource.id ? newSource : item;
  });

  // 更新aliasRelianceMap: source与artifacts的依赖关系
  const newAliasRelianceMap = upsertAliasRelianceMapByDataSource(
    oldSource,
    newSource,
    aliasRelianceMap
  );

  return {
    newDataSources: newDataSources,
    newAliasRelianceMap: newAliasRelianceMap,
  };
};

// 删除数据源
export const deleteDataSource = (
  source: DataSource,
  dataSources: DataSource[],
  artifacts: Artifact[]
): { newDataSources: DataSource[]; newAliasRelianceMap: AliasRelianceMap } => {
  // 删除节点
  const filteredDataSources = dataSources.filter(
    (item) => item.id !== source.id
  );

  // 正确地更新所有的source id
  const newDataSources = filteredDataSources.map((source, idx) => ({
    ...source,
    id: `source_${idx + 1}`,
  }));

  // 更新aliasRelianceMap: source与artifacts的依赖关系
  const newAliasRelianceMap = createAliasRelianceMap(newDataSources, artifacts);

  return {
    newDataSources,
    newAliasRelianceMap,
  };
};
