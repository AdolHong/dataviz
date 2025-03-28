// // 创建一个对象来存储 alias 和对应的 chart.id 列表
// const aliasMap = useState<{
//   [alias: string]: { title: string; id: string }[];
// }>(
//   demoReport.charts.reduce<{
//     [alias: string]: { title: string; id: string }[];
//   }>((acc, chart) => {
//     chart.dependencies.forEach((alias) => {
//       if (!acc[alias]) {
//         acc[alias] = []; // 如果 alias 不存在，初始化为一个空数组
//       }
//       acc[alias].push({ title: chart.title, id: chart.id }); // 将 chart.title 添加到对应的 alias 列表中
//     });
//     return acc;
//   }, {})
// );

import type { Chart } from '..';

export type AliasRelianceMap = {
  [alias: string]: { chartTitle: string; chartId: string }[];
};

export const updateAliasRelianceMap = (
  oldChart: Chart | null,
  newChart: Chart | null,
  aliasMap: AliasRelianceMap
) => {
  const updatedAliasMap = { ...aliasMap };

  // 删除旧图表的依赖  (新增chart时,oldChart为null)
  if (oldChart) {
    Object.keys(updatedAliasMap).forEach((alias) => {
      updatedAliasMap[alias] = updatedAliasMap[alias].filter(
        (chart) => chart.chartId !== oldChart.id
      );
    });
  }

  // 添加新图表的依赖  (删除chart时,newChart为null)
  if (newChart) {
    newChart.dependencies.forEach((alias) => {
      if (!updatedAliasMap[alias]) {
        updatedAliasMap[alias] = []; // 如果 alias 不存在，初始化为一个空数组
      }
      updatedAliasMap[alias].push({
        chartTitle: newChart.title,
        chartId: newChart.id,
      }); // 将 newChart.title 和 newChart.id 添加到对应的 alias 列表中
    });
  }

  return updatedAliasMap;
};
