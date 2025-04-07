// import { createFileRoute } from '@tanstack/react-router';
// import { useEffect, useRef } from 'react';
// import * as echarts from 'echarts';

// export const Route = createFileRoute('/dev/echart')({
//   component: RouteComponent,
// });

// // ECharts 图表渲染组件
// interface EChartComponentProps {
//   optionData: string; // JSON 字符串格式的 ECharts 配置
// }

// const EChartComponent: React.FC<EChartComponentProps> = ({ optionData }) => {
//   const chartRef = useRef<HTMLDivElement>(null);
//   const chartInstance = useRef<echarts.ECharts | null>(null);

//   useEffect(() => {
//     let parsedOption: echarts.EChartsOption;
//     try {
//       parsedOption = JSON.parse(optionData);
//     } catch (e) {
//       console.error('Failed to parse ECharts option data:', e);
//       // 可以在这里显示错误提示，或者渲染一个占位符
//       return; // 解析失败则不继续
//     }

//     // 初始化或更新图表
//     if (chartRef.current) {
//       // 如果实例不存在或已销毁，则初始化
//       if (!chartInstance.current || chartInstance.current.isDisposed()) {
//         chartInstance.current = echarts.init(chartRef.current);
//       }

//       // 设置配置项
//       chartInstance.current.setOption(parsedOption, true); // true 表示不合并，完全替换
//     }

//     // 添加窗口大小调整监听器
//     const handleResize = () => {
//       if (chartInstance.current && !chartInstance.current.isDisposed()) {
//         chartInstance.current.resize();
//       }
//     };

//     window.addEventListener('resize', handleResize);

//     // 清理函数：组件卸载时销毁图表实例并移除监听器
//     return () => {
//       window.removeEventListener('resize', handleResize);
//       if (chartInstance.current && !chartInstance.current.isDisposed()) {
//         chartInstance.current.dispose();
//         chartInstance.current = null; // 清空引用
//       }
//     };
//   }, [optionData]); // 当配置数据变化时，重新执行 effect

//   console.info('charRef', chartRef);

//   // 返回用于挂载 ECharts 的 div
//   return <div ref={chartRef} style={{ width: '100%', height: '100%' }} />;
// };

// function RouteComponent() {
//   return <div>Hello "/dev/echart"!</div>;
// }
