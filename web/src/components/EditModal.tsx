import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import DataSourceTab from './DataSourceTab';
import FilterTab from './FilterTab';
import ChartTab from './ChartTab';

import {
  Filter,
  Database,
  BarChart2,
  Pencil,
  Trash2,
  Plus,
} from 'lucide-react';
import { toast } from 'sonner';
import { DataSourceModal } from './DataSourceModal';
import { EditLayoutModal } from './EditLayoutModal';
import ConfirmDialog from './ConfirmDialog';

import type { DataSource, Layout, Parameter, Chart, Report } from '@/types';
import {
  addItem as addLayoutItem,
  removeEmptyRowsAndColumns,
} from '@/types/models/layout';

interface EditModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (params: any[], visualizations: any[], sqlCode: string) => void;
  reportId: string;
}

const EditModal = ({ open, onClose, reportId }: EditModalProps) => {
  // todo: 获取报表的布局
  console.log('reportId', reportId);
  // 构造 demo 数据
  const demoReport = {
    title: '销售报表',
    description: '这是一个销售数据的示例报表',
    dataSources: [
      {
        id: 'ds1',
        name: '主数据',
        type: 'python',
        alias: '销售数据',
        executor: { type: 'python', engine: 'pandas' },
        code: '',
      },
      {
        id: 'ds2',
        name: '外部数据',
        type: 'sql',
        alias: '外部数据',
        executor: { type: 'python', engine: 'pandas' },
        code: '',
      },
    ],
    parameters: [
      { name: '开始日期', type: 'single_select' },
      { name: '结束日期', type: 'single_select' },
    ],
    charts: [
      {
        id: 'item-1',
        title: '销售趋势',
        code: 'line',
        dependencies: ['ds1'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'item-2',
        title: '销售占比',
        code: 'pie',
        dependencies: ['ds2'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'item-3',
        title: '销售占比',
        code: 'pie',
        dependencies: ['ds2'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'item-4',
        title: '销售占比',
        code: 'pie',
        dependencies: ['ds2'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'item-5',
        title: '销售占比',
        code: 'pie',
        dependencies: ['ds2'],
        executor: { type: 'python', engine: 'pandas' },
      },
      {
        id: 'item-6',
        title: '销售占比',
        code: 'pie',
        dependencies: ['ds2'],
        executor: { type: 'python', engine: 'pandas' },
      },
    ],
    layout: {
      columns: 3,
      rows: 2,
      items: [
        { id: 'item-1', title: '销售趋势', width: 1, height: 1, x: 0, y: 0 },
        { id: 'item-2', title: '销售占比', width: 1, height: 1, x: 1, y: 0 },
        { id: 'item-3', title: '销售明细', width: 1, height: 1, x: 2, y: 0 },
        { id: 'item-4', title: '新增图表1', width: 1, height: 1, x: 0, y: 1 },
        { id: 'item-5', title: '新增图表2', width: 1, height: 1, x: 1, y: 1 },
        { id: 'item-6', title: '新增图表333', width: 1, height: 1, x: 2, y: 1 },
      ],
    },
  };

  const [dataSources, setDataSources] = useState<DataSource[]>(
    demoReport.dataSources
  );
  const [parameters, setParameters] = useState<Parameter[]>(
    demoReport.parameters
  );
  const [charts, setCharts] = useState<Chart[]>(demoReport.charts);
  const [layout, setLayout] = useState<Layout>(demoReport.layout);

  const [activeTab, setActiveTab] = useState('filters');
  const [isDataSourceModalOpen, setIsDataSourceModalOpen] = useState(false);
  const [isConfirmDeleteOpen, setIsConfirmDeleteOpen] = useState(false);
  const [deleteFunction, setDeleteFunction] = useState<(() => void) | null>(
    null
  );
  const [deleteMessage, setDeleteMessage] = useState<string>('');

  // 添加图表
  const handleAddChart = () => {
    // 提取现有图表的 ID，并转换为数字
    const existingIds = charts.map((chart) =>
      parseInt(chart.id.split('-')[1], 10)
    );

    // 找到缺失的最小数字
    let newId = 1;
    while (existingIds.includes(newId)) {
      newId++;
    }

    // 生成新的 ID
    const newChartId = `item-${newId}`;
    const title = `新增图表 ${newId}`;

    // 添加新的图表
    setCharts([
      ...charts,
      {
        id: newChartId,
        title: title,
        code: 'pie',
        dependencies: [],
        executor: { type: 'python', engine: 'pandas' },
      },
    ]);

    // 更新布局
    setLayout(addLayoutItem(layout, newChartId, title));
  };

  // 删除图表
  const handleDeleteChart = (chartId: string) => {
    if (charts.length === 1) {
      toast.error('至少需要保留一个图表');
      return;
    }
    // 删除图表
    setCharts(charts.filter((chart) => chart.id !== chartId));

    // 更新布局，删除对应的 item
    let newLayout = {
      ...layout,
      items: layout.items.filter((item) => item.id !== chartId), // 过滤掉被删除的 item
    };
    // 删除空行和空列
    newLayout = removeEmptyRowsAndColumns(newLayout);
    setLayout(newLayout);
    toast.success('图表已删除');
  };

  const confirmDelete = (deleteFunction: () => void, message: string) => {
    setIsConfirmDeleteOpen(true);
    setDeleteFunction(() => deleteFunction);
    setDeleteMessage(message);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className='max-w-[90vw] h-[90vh] flex flex-col'>
          <DialogHeader>
            <DialogTitle>编辑报表</DialogTitle>
          </DialogHeader>

          <Tabs
            value={activeTab}
            onValueChange={setActiveTab}
            className='flex-1 flex flex-col overflow-hidden'
          >
            <TabsList className='w-full grid grid-cols-3 sticky top-0 z-10'>
              <TabsTrigger value='data' className='flex items-center gap-2'>
                <Database size={24} />
                <span>数据源</span>
              </TabsTrigger>

              <TabsTrigger value='filters' className='flex items-center gap-2'>
                <Filter size={24} />
                <span>筛选条件</span>
              </TabsTrigger>

              <TabsTrigger value='charts' className='flex items-center gap-2'>
                <BarChart2 size={24} />
                <span>图表</span>
              </TabsTrigger>
            </TabsList>

            <div className='flex-1 overflow-y-auto'>
              <DataSourceTab
                dataSources={dataSources}
                setDataSources={setDataSources}
                handleDeleteDataSource={() => {}}
                setIsDataSourceModalOpen={setIsDataSourceModalOpen}
                confirmDelete={confirmDelete}
              />
              <FilterTab
                parameters={parameters}
                setParameters={setParameters}
                handleDeleteParameter={() => {}}
                confirmDelete={confirmDelete}
              />
              <ChartTab
                layout={layout}
                setLayout={setLayout}
                handleAddChart={handleAddChart}
                handleDeleteChart={handleDeleteChart}
                confirmDelete={confirmDelete}
              />
            </div>
          </Tabs>
        </DialogContent>
      </Dialog>

      <DataSourceModal
        open={isDataSourceModalOpen}
        onClose={() => setIsDataSourceModalOpen(false)}
        onSave={() => {}}
      />

      {/* 确认删除对话框 */}
      <ConfirmDialog
        open={isConfirmDeleteOpen}
        onClose={() => setIsConfirmDeleteOpen(false)}
        onConfirm={() => {
          if (deleteFunction) {
            deleteFunction();
          }
          setIsConfirmDeleteOpen(false);
        }}
        title='确认删除'
        message={deleteMessage}
      />
    </>
  );
};

export default EditModal;
