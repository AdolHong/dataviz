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
import { demoFileSystemData } from '@/data/demoFileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';
import type { ReportResponse } from '@/types';
import { reportApi } from '@/api/report';

export function DashboardPage() {
  const [fileSystemItems, setFileSystemItems] =
    useState<FileSystemItem[]>(demoFileSystemData);
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);
  const [dashboardData, setDashboardData] = useState<ReportResponse | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const { dashboardId, setDashboardId } = useStore();

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
      } catch (error) {
        console.error('获取报表数据失败:', error);
        // 使用一些示例数据
        setDashboardData({
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
                width: 1,
                height: 1,
                x: 2,
                y: 0,
              },
            ],
          },
        });
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

  return (
    <div className='flex h-screen'>
      {/* 左侧导航栏 */}
      <div className='w-64 border-r bg-background p-4 overflow-auto'>
        <FileExplorer
          items={fileSystemItems}
          onItemsChange={handleFileSystemChange}
          onSelectItem={handleSelectItem}
        />
      </div>

      {/* 右侧内容区 */}
      <div className='flex-1 overflow-auto'>
        <div className='container mx-auto p-6 space-y-6'>
          {loading ? (
            <div className='flex items-center justify-center h-64'>
              <p className='text-muted-foreground'>加载中...</p>
            </div>
          ) : !selectedItem || selectedItem.type !== 'file' ? (
            <div className='flex items-center justify-center h-64'>
              <p className='text-muted-foreground'>请从左侧选择一个报表文件</p>
            </div>
          ) : (
            <>
              {/* 标题和描述 */}
              <div>
                <h1 className='text-3xl font-bold'>
                  {dashboardData?.title || selectedItem.name}
                </h1>
                <p className='text-muted-foreground'>
                  {dashboardData?.description || '无描述'}
                </p>
              </div>

              {/* 参数区域 */}
              <Card>
                <CardHeader className='pb-3'>
                  <CardTitle>查询参数</CardTitle>
                  <CardDescription>设置过滤条件</CardDescription>
                </CardHeader>
                <CardContent className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4'>
                  {dashboardData?.parameters.map((param) => (
                    <div key={param.id} className='space-y-2'>
                      <label className='text-sm font-medium'>
                        {param.alias || param.name}
                      </label>
                      <Input placeholder={param.config.default.toString()} />
                    </div>
                  ))}
                </CardContent>
                <div className='flex justify-end px-6 pb-6'>
                  <Button>查询</Button>
                </div>
              </Card>

              {/* 展示区域 */}
              <div className='space-y-6'>
                <h2 className='text-lg font-medium mb-2'>数据可视化</h2>
                <div className='grid grid-cols-3 gap-4'>
                  {dashboardData?.layout.items.map((item) => (
                    <Card key={item.id} className='col-span-1'>
                      <CardHeader>
                        <CardTitle className='text-lg'>{item.title}</CardTitle>
                      </CardHeader>
                      <CardContent className='h-64 border-2 border-dashed border-muted-foreground/20 rounded-md flex items-center justify-center'>
                        <p className='text-muted-foreground'>
                          {item.title} 内容
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
