import type { Artifact, DataSource } from '..';

// 可视化参数接口
export interface AliasRelianceMap {
  aliasToArtifacts: {
    [alias: string]: { artifactTitle: string; artifactId: string }[];
  };
  aliasToDataSourceId: {
    [alias: string]: string;
  };
}

export const updateAliasRelianceMapByArtifact = (
  oldArtifact: Artifact | null,
  newArtifact: Artifact | null,
  aliasMap: AliasRelianceMap
) => {
  const updatedAliasMap = { ...aliasMap };

  // 删除旧图表的依赖  (新增artifact时,oldArtifact为null)
  if (oldArtifact) {
    Object.keys(updatedAliasMap.aliasToArtifacts).forEach((alias) => {
      updatedAliasMap.aliasToArtifacts[alias] =
        updatedAliasMap.aliasToArtifacts[alias].filter(
          (artifact) => artifact.artifactId !== oldArtifact.id
        );
    });
  }

  // 添加新图表的依赖  (删除artifact时,newArtifact为null)
  if (newArtifact) {
    newArtifact.dependencies.forEach((alias) => {
      if (!updatedAliasMap.aliasToArtifacts[alias]) {
        updatedAliasMap.aliasToArtifacts[alias] = []; // 如果 alias 不存在，初始化为一个空数组
      }
      updatedAliasMap.aliasToArtifacts[alias].push({
        artifactTitle: newArtifact.title,
        artifactId: newArtifact.id,
      }); // 将 newArtifact.title 和 newArtifact.id 添加到对应的 alias 列表中
    });
  }

  return updatedAliasMap;
};

// datasource: 新增修改时， 需要更新aliasMap
export const upsertAliasRelianceMapByDataSource = (
  oldDataSource: DataSource | null,
  newDataSource: DataSource,
  aliasMap: AliasRelianceMap
) => {
  const updatedAliasMap = { ...aliasMap };

  // 删除旧数据源的依赖  (新增datasource时,oldDataSource为null)
  if (oldDataSource) {
    Object.keys(updatedAliasMap.aliasToDataSourceId).forEach((alias) => {
      if (updatedAliasMap.aliasToDataSourceId[alias] === oldDataSource.id) {
        // 删除旧alias 对应的datasource id
        delete updatedAliasMap.aliasToDataSourceId[alias];
      }
    });
  }
  updatedAliasMap.aliasToDataSourceId[newDataSource.alias] = newDataSource.id;
  return updatedAliasMap;
};

// 根据dataSources和artifacts， 构建aliasRelianceMap
export const createAliasRelianceMap = (
  dataSources: DataSource[],
  artifacts: Artifact[]
): AliasRelianceMap => {
  const aliasToArtifacts = artifacts.reduce<{
    aliasToArtifacts: {
      [alias: string]: { artifactTitle: string; artifactId: string }[];
    };
  }>((acc, artifact) => {
    artifact.dependencies.forEach((alias) => {
      if (!acc[alias]) {
        acc[alias] = []; // 如果 alias 不存在，初始化为一个空数组
      }
      acc[alias].push({
        artifactTitle: artifact.title,
        artifactId: artifact.id,
      }); // 将 artifact.title 添加到对应的 alias 列表中
    });
    return acc;
  }, {});

  const aliasToDataSourceId = dataSources.reduce<{
    aliasToDataSourceId: { [alias: string]: string };
  }>((acc, dataSource) => {
    acc[dataSource.alias] = dataSource.id; // 将数据源的别名映射到其ID
    return acc;
  }, {});

  const aliasRelianceMap: AliasRelianceMap = {
    aliasToArtifacts,
    aliasToDataSourceId,
  };

  return aliasRelianceMap;
};
