import { Button } from '@/components/ui/button';
import { useState, useEffect } from 'react';
import { useStore } from '@/lib/store';
import { FileExplorer } from '@/pages/dashboard/FileExplorer';
import { LayoutGrid } from '@/pages/dashboard/LayoutGrid';
import { demoFileSystemData } from '@/data/demoFileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';
import type { ReportResponse } from '@/types';
import { reportApi } from '@/api/report';
import type { Layout } from '@/types/models/layout';
import { toast } from 'sonner';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { ParameterQueryArea } from '@/pages/dashboard/ParameterQueryArea';
import { type Parameter } from '@/types/models/parameter';

// 示例参数，实际使用时可能从API获取
const exampleParameters: Parameter[] = [
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
    id: 'param2',
    name: 'startDate',
    alias: '开始日期',
    config: {
      type: 'date_picker',
      dateFormat: 'yyyy-MM-dd',
      default: '',
    },
  },
  {
    id: 'param3',
    name: 'endDate',
    alias: '结束日期',
    config: {
      type: 'date_picker',
      dateFormat: 'yyyy-MM-dd',
      default: '',
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
      default: [],
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
      default: '',
    },
  },
  {
    id: 'param6',
    name: 'tags',
    alias: '标签',
    description: '输入多个标签进行筛选',
    config: {
      type: 'multi_input',
      default: [''],
      sep: ',',
      wrapper: '',
    },
  },
];

export function DashboardPage() {
  const [fileSystemItems, setFileSystemItems] =
    useState<FileSystemItem[]>(demoFileSystemData);
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);
  const [dashboardData, setDashboardData] = useState<ReportResponse | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const { dashboardId, setDashboardId } = useStore();

  const [layout, setLayout] = useState<Layout | null>(null);

  // 添加导航栏显示控制状态
  const [navbarVisible, setNavbarVisible] = useState(true);
  const [navbarWidth, setNavbarWidth] = useState(256); // 默认宽度为64 (16rem)

  const [requireFileUpload, setRequireFileUpload] = useState(true);
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

  // 当选择一个文件时，加载该文件对应的reportId的数据
  useEffect(() => {
    if (!selectedItem || selectedItem.type !== 'file') return;

    const loadReportData = async () => {
      try {
        setLoading(true);
        // 使用selectedItem的reportId
        setDashboardId(selectedItem.reportId);
        const response = await reportApi.getReportConfig(selectedItem.reportId);
        setDashboardData(response);
        setLayout(response.layout);
      } catch (error) {
        console.error('获取报表数据失败:', error);
        // 使用一些示例数据
        const demoData = {
          id: selectedItem.reportId,
          title: selectedItem.name,
          description: '这是一个示例报表描述',
          dataSources: [],
          parameters: [
            {
              id: 'param1',
              name: 'region',
              alias: '区域',
              config: {
                type: 'single_select',
                choices: ['华东', '华南', '华北'],
                default: '华东',
              },
            },
            {
              id: 'param2',
              name: 'category',
              alias: '分类',
              config: {
                type: 'single_select',
                choices: ['电子产品', '服装', '食品'],
                default: '电子产品',
              },
            },
            {
              id: 'param3',
              name: 'date',
              alias: '日期',
              config: {
                type: 'date_picker',
                dateFormat: 'YYYY-MM-DD',
                default: '2023-01-30',
              },
            },
            {
              id: 'param4',
              name: 'min_price',
              alias: '最低价格',
              config: { type: 'single_input', default: '100' },
            },
          ],
          artifacts: [],
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
                width: 3,
                height: 1,
                x: 0,
                y: 1,
              },
            ],
          },
        };
        setDashboardData(demoData);
        setLayout(demoData.layout);
      } finally {
        setLoading(false);
      }
    };

    loadReportData();
  }, [selectedItem, setDashboardId]);

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

  // 布局变更处理
  const handleLayoutChange = (newLayout: Layout) => {
    setLayout(newLayout);
  };

  // 保存布局
  const handleSaveLayout = () => {
    if (!layout) return;

    // 模拟保存布局的API调用
    setTimeout(() => {
      toast.success('布局已保存');
      setEditMode(false);
      // 如果有后端API，可以在这里调用
    }, 500);
  };

  // 重置布局
  const handleResetLayout = () => {
    if (dashboardData?.layout) {
      setLayout(dashboardData.layout);
      toast.info('布局已重置');
    }
  };

  const handleQuerySubmit = (values: Record<string, any>) => {
    console.log('查询参数:', values);
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
          <span className='text-xl font-semibold'>数据分析平台</span>
        </div>
      </div>

      <div className='flex flex-1 overflow-hidden'>
        {/* 左侧导航栏 */}
        <div
          className='border-r bg-background overflow-auto transition-all duration-300 ease-in-out'
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
        <div className='flex-1 overflow-auto'>
          <div className='container mx-auto py-6 px-8 space-y-6'>
            {loading ? (
              <div className='flex items-center justify-center h-64'>
                <p className='text-muted-foreground'>加载中...</p>
              </div>
            ) : !selectedItem || selectedItem.type !== 'file' ? (
              <div className='flex flex-col items-center justify-center h-64 text-center'>
                <p className='text-muted-foreground mb-2'>
                  请从左侧选择一个报表文件
                </p>
                <p className='text-xs text-muted-foreground/70'>
                  选择后将展示报表内容与配置
                </p>
              </div>
            ) : (
              <>
                {/* 标题和描述 */}
                <div className='border-b pb-4'>
                  <h1 className='text-2xl font-semibold'>
                    {dashboardData?.title || selectedItem.name}
                  </h1>
                  <p className='text-muted-foreground mt-1'>
                    {dashboardData?.description || '无描述'}
                  </p>
                </div>

                {/* 参数区域 */}
                <div className='space-y-2'>
                  <ParameterQueryArea
                    parameters={exampleParameters}
                    onSubmit={handleQuerySubmit}
                    requireFileUpload={requireFileUpload}
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
