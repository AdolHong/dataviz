import type { Chart, DataSource } from '..';

// 可视化参数接口
export interface AliasRelianceMap {
  aliasToCharts: {
    [alias: string]: { chartTitle: string; chartId: string }[];
  };
  aliasToDataSourceId: {
    [alias: string]: string;
  };
}

export const updateAliasRelianceMapByChart = (
  oldChart: Chart | null,
  newChart: Chart | null,
  aliasMap: AliasRelianceMap
) => {
  const updatedAliasMap = { ...aliasMap };

  // 删除旧图表的依赖  (新增chart时,oldChart为null)
  if (oldChart) {
    Object.keys(updatedAliasMap.aliasToCharts).forEach((alias) => {
      updatedAliasMap.aliasToCharts[alias] = updatedAliasMap.aliasToCharts[
        alias
      ].filter((chart) => chart.chartId !== oldChart.id);
    });
  }

  // 添加新图表的依赖  (删除chart时,newChart为null)
  if (newChart) {
    newChart.dependencies.forEach((alias) => {
      if (!updatedAliasMap.aliasToCharts[alias]) {
        updatedAliasMap.aliasToCharts[alias] = []; // 如果 alias 不存在，初始化为一个空数组
      }
      updatedAliasMap.aliasToCharts[alias].push({
        chartTitle: newChart.title,
        chartId: newChart.id,
      }); // 将 newChart.title 和 newChart.id 添加到对应的 alias 列表中
    });
  }

  return updatedAliasMap;
};

// datasource: 新增删除修改时， 需要更新aliasMap
export const updateAliasRelianceMapByDataSource = (
  oldDataSource: DataSource | null,
  newDataSource: DataSource | null,
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

  // 添加新数据源的依赖  (删除datasource时,newDataSource为null)
  if (newDataSource) {
    updatedAliasMap.aliasToDataSourceId[newDataSource.alias] = newDataSource.id;
  }

  return updatedAliasMap;
};
