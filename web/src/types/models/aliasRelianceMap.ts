import type { Artifact, DataSource } from '..';

// 可视化参数接口
type AliasRelianceMapValue = {
  artifactTitle: string;
  artifactId: string;
};

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

  // 删除aliasToArtifacts中, 列表为空的alias
  Object.keys(updatedAliasMap.aliasToArtifacts).forEach((alias) => {
    if (updatedAliasMap.aliasToArtifacts[alias].length === 0) {
      delete updatedAliasMap.aliasToArtifacts[alias];
    }
  });

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

  // 删除aliasToArtifacts中, 列表为空的alias
  Object.keys(updatedAliasMap.aliasToArtifacts).forEach((alias) => {
    if (updatedAliasMap.aliasToArtifacts[alias].length === 0) {
      delete updatedAliasMap.aliasToArtifacts[alias];
    }
  });

  return updatedAliasMap;
};

// 根据dataSources和artifacts， 构建aliasRelianceMap
export const createAliasRelianceMap = (
  dataSources: DataSource[],
  artifacts: Artifact[]
): AliasRelianceMap => {
  // 修改这里，直接使用正确的类型结构初始化
  const aliasToArtifacts: Record<string, AliasRelianceMapValue[]> = {};

  // 遍历所有图表，收集依赖关系
  artifacts.forEach((artifact) => {
    artifact.dependencies.forEach((alias) => {
      if (!aliasToArtifacts[alias]) {
        aliasToArtifacts[alias] = [];
      }
      aliasToArtifacts[alias].push({
        artifactTitle: artifact.title,
        artifactId: artifact.id,
      });
    });
  });

  // 构建数据源映射
  const aliasToDataSourceId: Record<string, string> = {};
  dataSources.forEach((dataSource) => {
    aliasToDataSourceId[dataSource.alias] = dataSource.id;
  });

  return {
    aliasToArtifacts,
    aliasToDataSourceId,
  };
};

// // 确保创建 AliasRelianceMap 实例时完全匹配接口
// const exampleMap: AliasRelianceMap = {
//   aliasToArtifacts: {
//     // 必须是 { artifactTitle: string; artifactId: string }[] 类型
//     someAlias: [{ artifactTitle: 'Example Title', artifactId: 'example-id' }],
//   },
//   aliasToDataSourceId: {
//     // 必须是 { [alias: string]: string } 类型
//     someAlias: 'dataSourceId',
//   },
// };
