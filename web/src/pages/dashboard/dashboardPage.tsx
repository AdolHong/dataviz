import { Button } from '@/components/ui/button';
import { useState, useEffect } from 'react';
import { useStore } from '@/lib/store';
import { FileExplorer } from '@/pages/dashboard/FileExplorer';
import { LayoutGrid } from '@/pages/dashboard/LayoutGrid';
import { demoFileSystemData } from '@/data/demoFileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';
import type { ReportResponse } from '@/types';
import type { Layout } from '@/types/models/layout';
import { toast } from 'sonner';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { ParameterQueryArea } from '@/pages/dashboard/ParameterQueryArea';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

const demoReportResponse: ReportResponse = {
  id: 'report-1',
  title: '销售报表',
  description: '这是一个销售数据的示例报表',
  dataSources: [
    {
      id: 'source-1',
      name: '主数据',
      alias: 'df_sales',
      executor: {
        type: 'sql',
        engine: 'default',
        code: 'select 1',
        updateMode: { type: 'manual' },
      },
    },
    {
      id: 'source-2',
      name: '外部数据',
      alias: 'df_external',
      executor: {
        type: 'python',
        engine: 'default',
        code: 'result = df.groupby("category").sum()',
        updateMode: { type: 'manual' },
      },
    },
    {
      id: 'source-3',
      name: '品类销量',
      alias: 'df_category',
      executor: {
        type: 'csv_uploader',
        demoData: 'category,sales\nA,100\nB,200\nC,300',
      },
    },
    {
      id: 'source-4',
      name: 'csv数据',
      alias: 'df_csv_data',
      executor: { type: 'csv_data', data: 'a,b,c\n1,2,3\n4,5,6' },
    },
    {
      id: 'source-5',
      name: '月度预算',
      alias: 'df_budget',
      executor: {
        type: 'csv_uploader',
        demoData: 'month,budget\n1,1000\n2,2000\n3,3000',
      },
    },
  ],
  parameters: [
    {
      id: 'p1',
      name: 'start_date',
      alias: '开始日期', // 可选字段
      description: '选择开始日期',
      config: {
        type: 'single_select',
        choices: ['2023-01-01', '2023-01-02', '2023-01-03'],
        default: '2023-01-02',
      },
    },
    {
      id: 'p2',
      name: 'end_date',
      alias: '结束日期', // 可选字段
      description: '选择结束日期',
      config: {
        type: 'date_picker',
        default: '2023-01-04',
        dateFormat: 'YYYY-MM-DD',
      },
    },
    {
      id: 'param1',
      name: 'period',
      alias: '周期',
      description: '选择报表的统计周期',
      config: {
        type: 'single_select',
        choices: ['日', '周', '月', '季', '年'],
        default: '月',
      },
    },
    {
      id: 'param4',
      name: 'department',
      alias: '部门',
      description: '选择需要查看的部门',
      config: {
        type: 'multi_select',
        choices: ['销售部', '技术部', '市场部', '人力资源部', '财务部'],
        default: ['销售部', '技术部'],
        sep: ',',
        wrapper: '',
      },
    },
    {
      id: 'param5',
      name: 'keyword',
      alias: '关键词',
      config: {
        type: 'single_input',
        default: 'hi',
      },
    },
    {
      id: 'param6',
      name: 'tags',
      alias: '标签',
      description: '输入多个标签进行筛选',
      config: {
        type: 'multi_input',
        default: ['tag1', 'tag2', 'tag3'],
        sep: ',',
        wrapper: '',
      },
    },
  ],
  artifacts: [
    {
      id: 'artifact-1',
      title: '销售趋势',
      code: 'line',
      dependencies: ['df_sales'],
      executor_engine: 'default',
    },
    {
      id: 'artifact-2',
      title: '销售占比',
      code: 'pie',
      dependencies: ['df_external'],
      executor_engine: 'default',
    },
    {
      id: 'artifact-3',
      title: '销售明细',
      code: 'pie',
      dependencies: ['df_external'],
      executor_engine: 'default',
    },
    {
      id: 'artifact-4',
      title: '新增图表1',
      code: 'pie',
      dependencies: ['df_sales', 'df_external'],
      executor_engine: 'default',
    },
    {
      id: 'artifact-5',
      title: '新增图表2',
      code: 'pie',
      dependencies: ['df_sales'],
      executor_engine: 'default',
    },
  ],
  layout: {
    columns: 3,
    rows: 2,
    items: [
      {
        id: 'artifact-1',
        title: '销售趋势',
        width: 1,
        height: 1,
        x: 0,
        y: 0,
      },
      {
        id: 'artifact-2',
        title: '销售占比',
        width: 1,
        height: 1,
        x: 1,
        y: 0,
      },
      {
        id: 'artifact-3',
        title: '销售明细',
        width: 1,
        height: 1,
        x: 2,
        y: 0,
      },
      {
        id: 'artifact-4',
        title: '新增图表1',
        width: 1,
        height: 1,
        x: 0,
        y: 1,
      },
      {
        id: 'artifact-5',
        title: '新增图表2',
        width: 1,
        height: 1,
        x: 1,
        y: 1,
      },
    ],
  },
};

export function DashboardPage() {
  const [fileSystemItems, setFileSystemItems] =
    useState<FileSystemItem[]>(demoFileSystemData);
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);
  const [dashboardData, setDashboardData] = useState<ReportResponse | null>(
    null
  );

  const [layout, setLayout] = useState<Layout | null>(null);

  // 添加导航栏显示控制状态
  const [navbarVisible, setNavbarVisible] = useState(true);
  const [navbarWidth, setNavbarWidth] = useState(256); // 默认宽度为64 (16rem)

  const [queryResults, setQueryResults] = useState<Record<string, any> | null>(
    null
  );

  // 切换导航栏显示状态
  const toggleNavbar = () => {
    setNavbarVisible(!navbarVisible);
  };

  // 根据选中文件的文件名长度调整导航栏宽度
  useEffect(() => {
    if (selectedItem && selectedItem.name) {
      // 计算一个基础宽度，每个字符大约10px，最小256px，最大400px
      const nameLength = selectedItem.name.length;
      const calculatedWidth = Math.min(Math.max(256, nameLength * 10), 400);
      setNavbarWidth(calculatedWidth);
    }
  }, [selectedItem]);

  // 使用 demoReportResponse 作为默认选择的报表数据
  useEffect(() => {
    if (!selectedItem || selectedItem.type !== 'file') {
      // 设置默认的demoReportResponse
      setDashboardData(demoReportResponse);
      setLayout(demoReportResponse.layout);
    }
  }, [selectedItem]);

  // 处理文件系统项目变更
  const handleFileSystemChange = (items: FileSystemItem[]) => {
    setFileSystemItems(items);
  };

  // 处理选择文件系统项目
  const handleSelectItem = (item: FileSystemItem) => {
    setSelectedItem(item);
    // 如果选择的是文件，将其报表ID设置到store中
    if (item.type === 'file') {
      setDashboardId(item.reportId);
    }
  };

  // 处理图表项点击
  const handleChartItemClick = (itemId: string) => {
    console.log('点击了图表项:', itemId);
    // 这里可以添加查看或编辑图表的逻辑
  };

  // 修改handleQuerySubmit函数，接收文件参数为对象
  const handleQuerySubmit = (
    values: Record<string, any>,
    files?: Record<string, File[]>
  ) => {
    console.log('查询参数:', values);
    console.log('上传文件:', files);
    setQueryResults(values);
    // 这里可以添加API调用逻辑
  };

  return (
    <div className='flex flex-col h-screen relative'>
      {/* 顶部Header */}
      <div className='border-b bg-background flex items-center h-14 px-4'>
        <div className='flex items-center space-x-2'>
          <svg
            className='h-6 w-6 text-blue-500'
            viewBox='0 0 24 24'
            fill='none'
            stroke='currentColor'
            strokeWidth='2'
            strokeLinecap='round'
            strokeLinejoin='round'
          >
            <polyline points='22 12 18 12 15 21 9 3 6 12 2 12'></polyline>
          </svg>
          <span className='text-xl font-semibold'>DataViz</span>
        </div>
      </div>

      <div className='flex flex-1 overflow-hidden'>
        {/* 左侧导航栏 */}
        <div
          className='border-r bg-background overflow-auto transition-all duration-300 ease-in-out flex-shrink-0'
          style={{
            width: navbarVisible ? `${navbarWidth}px` : '0px',
            opacity: navbarVisible ? 1 : 0,
            visibility: navbarVisible ? 'visible' : 'hidden',
          }}
        >
          <FileExplorer
            items={fileSystemItems}
            onItemsChange={handleFileSystemChange}
            onSelectItem={handleSelectItem}
          />
        </div>

        {/* 导航栏切换按钮 */}
        <div className='absolute top-100 left-0 z-10'>
          <Button
            variant='ghost'
            size='icon'
            className={`rounded-full ml-${navbarVisible ? navbarWidth / 4 : '0'} bg-secondary shadow-md`}
            onClick={toggleNavbar}
          >
            {navbarVisible ? (
              <ChevronLeft size={16} />
            ) : (
              <ChevronRight size={16} />
            )}
          </Button>
        </div>

        {/* 右侧内容区 */}
        <div className='flex-1 w-0 min-w-0 overflow-auto'>
          <div className='container max-w-full py-6 px-4 md:px-8 space-y-6'>
            {selectedItem && selectedItem.type === 'file' && (
              // 显示选中的报表
              <>
                <div>
                  <div className='space-y-2'>
                    <Tooltip>
                      <TooltipTrigger>
                        <h1 className='text-2xl font-semibold'>
                          {demoReportResponse.title}
                        </h1>
                      </TooltipTrigger>
                      {demoReportResponse.description && (
                        <TooltipContent>
                          <p>{demoReportResponse.description}</p>
                        </TooltipContent>
                      )}
                    </Tooltip>
                  </div>
                </div>

                {/* 参数区域 */}
                <div className='space-y-2'>
                  <ParameterQueryArea
                    parameters={dashboardData?.parameters || []}
                    dataSources={dashboardData?.dataSources || []}
                    onSubmit={handleQuerySubmit}
                  />
                </div>

                {/* 展示区域 */}
                <div className='space-y-4'>
                  <div className='flex items-center justify-between'>
                    <h2 className='text-lg font-medium'>数据可视化</h2>
                  </div>
                  {layout && layout.items.length > 0 && (
                    <LayoutGrid
                      layout={layout}
                      onItemClick={handleChartItemClick}
                    />
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
