// import type { ReportResponse } from '@/types';

// // 构造 demo 数据
// export const demoReportResponse: ReportResponse = {
//   id: 'report-1',
//   title: '销售报表',
//   description: '这是一个销售数据的示例报表',
//   dataSources: [
//     {
//       id: 'source-1',
//       name: '主数据',
//       alias: 'df_sales',
//       executor: {
//         type: 'sql',
//         engine: 'default',
//         code: 'select 1',
//         updateMode: { type: 'manual' },
//       },
//     },
//     {
//       id: 'source-2',
//       name: '外部数据',
//       alias: 'df_external',
//       executor: {
//         type: 'python',
//         engine: 'default',
//         code: 'result = df.groupby("category").sum()',
//         updateMode: { type: 'manual' },
//       },
//     },
//     {
//       id: 'source-3',
//       name: '品类销量',
//       alias: 'df_category',
//       executor: {
//         type: 'csv_uploader',
//         demoData: 'category,sales\nA,100\nB,200\nC,300',
//       },
//     },
//     {
//       id: 'source-4',
//       name: 'csv数据',
//       alias: 'df_csv_data',
//       executor: { type: 'csv_data', data: 'a,b,c\n1,2,3\n4,5,6' },
//     },
//     {
//       id: 'source-5',
//       name: '月度预算',
//       alias: 'df_budget',
//       executor: {
//         type: 'csv_uploader',
//         demoData: 'month,budget\n1,1000\n2,2000\n3,3000',
//       },
//     },
//   ],
//   parameters: [
//     {
//       id: 'p1',
//       name: 'start_date',
//       alias: '开始日期', // 可选字段
//       description: '选择开始日期',
//       config: {
//         type: 'single_select',
//         choices: ['2023-01-01', '2023-01-02', '2023-01-03'],
//         default: '2023-01-02',
//       },
//     },
//     {
//       id: 'p2',
//       name: 'end_date',
//       alias: '结束日期', // 可选字段
//       description: '选择结束日期',
//       config: {
//         type: 'date_picker',
//         default: '2023-01-04',
//         dateFormat: 'YYYY-MM-DD',
//       },
//     },
//     {
//       id: 'param1',
//       name: 'period',
//       alias: '周期',
//       description: '选择报表的统计周期',
//       config: {
//         type: 'single_select',
//         choices: ['日', '周', '月', '季', '年'],
//         default: '月',
//       },
//     },
//     {
//       id: 'param4',
//       name: 'department',
//       alias: '部门',
//       description: '选择需要查看的部门',
//       config: {
//         type: 'multi_select',
//         choices: ['销售部', '技术部', '市场部', '人力资源部', '财务部'],
//         default: ['销售部', '技术部'],
//         sep: ',',
//         wrapper: '',
//       },
//     },
//     {
//       id: 'param5',
//       name: 'keyword',
//       alias: '关键词',
//       config: {
//         type: 'single_input',
//         default: 'hi',
//       },
//     },
//     {
//       id: 'param6',
//       name: 'tags',
//       alias: '标签',
//       description: '输入多个标签进行筛选',
//       config: {
//         type: 'multi_input',
//         default: ['tag1', 'tag2', 'tag3'],
//         sep: ',',
//         wrapper: '',
//       },
//     },
//   ],
//   artifacts: [
//     {
//       id: 'artifact-1',
//       title: '销售趋势',
//       code: 'line',
//       dependencies: ['df_sales'],
//       executor_engine: 'default',
//     },
//     {
//       id: 'artifact-2',
//       title: '销售占比',
//       code: 'pie',
//       dependencies: ['df_external'],
//       executor_engine: 'default',
//     },
//     {
//       id: 'artifact-3',
//       title: '销售明细',
//       code: 'pie',
//       dependencies: ['df_external'],
//       executor_engine: 'default',
//     },
//     {
//       id: 'artifact-4',
//       title: '新增图表1',
//       code: 'pie',
//       dependencies: ['df_sales', 'df_external'],
//       executor_engine: 'default',
//     },
//     {
//       id: 'artifact-5',
//       title: '新增图表2',
//       code: 'pie',
//       dependencies: ['df_sales'],
//       executor_engine: 'default',
//     },
//   ],
//   layout: {
//     columns: 3,
//     rows: 2,
//     items: [
//       {
//         id: 'artifact-1',
//         title: '销售趋势',
//         width: 1,
//         height: 1,
//         x: 0,
//         y: 0,
//       },
//       {
//         id: 'artifact-2',
//         title: '销售占比',
//         width: 1,
//         height: 1,
//         x: 1,
//         y: 0,
//       },
//       {
//         id: 'artifact-3',
//         title: '销售明细',
//         width: 1,
//         height: 1,
//         x: 2,
//         y: 0,
//       },
//       {
//         id: 'artifact-4',
//         title: '新增图表1',
//         width: 1,
//         height: 1,
//         x: 0,
//         y: 1,
//       },
//       {
//         id: 'artifact-5',
//         title: '新增图表2',
//         width: 1,
//         height: 1,
//         x: 1,
//         y: 1,
//       },
//     ],
//   },
// };
