import type { DataSource } from './dataSource';
import type { Parameter } from './parameter';
import type { Chart } from './chart';
import type { Layout } from './layout';
import type { AliasRelianceMap } from '@/types';
import { updateAliasRelianceMapByDataSource } from '@/types';

// 主要响应接口
export interface Report {
  id: string; // 自动生成
  title: string;
  description?: string;
  dataSources: DataSource[];
  parameters: Parameter[]; // 使用之前定义的 Parameter 接口
  charts: Chart[];
  layout: Layout;
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

  // 更新aliasRelianceMap: source与charts的依赖关系
  const newAliasRelianceMap = updateAliasRelianceMapByDataSource(
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

  // 更新aliasRelianceMap: source与charts的依赖关系
  const newAliasRelianceMap = updateAliasRelianceMapByDataSource(
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
  aliasRelianceMap: AliasRelianceMap
): { newDataSources: DataSource[]; newAliasRelianceMap: AliasRelianceMap } => {
  // 删除节点
  const newDataSources = dataSources.filter((item) => item.id !== source.id);

  // 更新所有的source id
  newDataSources.map((source, idx) => {
    const newDataSource: DataSource = {
      ...source,
      id: `source_${idx + 1}`,
    };
    return newDataSource;
  });

  // 更新aliasRelianceMap: source与charts的依赖关系
  const newAliasRelianceMap = updateAliasRelianceMapByDataSource(
    source,
    null,
    aliasRelianceMap
  );

  return {
    newDataSources: newDataSources,
    newAliasRelianceMap: newAliasRelianceMap,
  };
};
