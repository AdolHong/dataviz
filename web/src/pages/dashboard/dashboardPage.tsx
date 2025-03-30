import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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

  return (
    <div className='flex h-screen relative'>
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
              <Card className='shadow-sm'>
                <CardHeader className='pb-2'>
                  <CardTitle className='text-base'>查询参数</CardTitle>
                  <CardDescription>设置报表过滤条件</CardDescription>
                </CardHeader>
                <CardContent className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4'>
                  {dashboardData?.parameters.map((param) => (
                    <div key={param.id} className='space-y-1.5'>
                      <label className='text-sm font-medium'>
                        {param.alias || param.name}
                      </label>
                      <Input placeholder={param.config.default.toString()} />
                    </div>
                  ))}
                </CardContent>
                <div className='flex justify-end px-6 pb-4'>
                  <Button>查询</Button>
                </div>
              </Card>

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
  );
}
