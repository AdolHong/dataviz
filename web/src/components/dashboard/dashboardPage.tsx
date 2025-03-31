import { Button } from '@/components/ui/button';
import { useState, useEffect } from 'react';
import { useStore } from '@/lib/store';
import { FileExplorer } from '@/components/dashboard/FileExplorer';
import { demoFileSystemData } from '@/data/demoFileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';
import type { ReportResponse } from '@/types';
import type { Layout } from '@/types/models/layout';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { DashboardContent } from '@/components/dashboard/DashboardContent';
import { demoReportResponse } from '@/data/demoReport';

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
        {selectedItem && selectedItem.type === 'file' && (
          <DashboardContent
            title={demoReportResponse.title}
            description={demoReportResponse?.description || ''}
            parameters={demoReportResponse?.parameters || []}
            dataSources={demoReportResponse?.dataSources || []}
            layout={demoReportResponse?.layout || []}
            handleQuerySubmit={handleQuerySubmit}
          />
        )}
      </div>
    </div>
  );
}
