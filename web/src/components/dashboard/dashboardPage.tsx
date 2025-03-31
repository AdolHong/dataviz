import { Button } from '@/components/ui/button';
import { useState, useEffect } from 'react';
import { useStore } from '@/lib/store';
import { FileExplorer } from '@/components/dashboard/FileExplorer';
import { demoFileSystemData } from '@/data/demoFileSystem';
import type { FileSystemItem } from '@/types/models/fileSystem';
import type { ReportResponse } from '@/types';
import type { Layout } from '@/types/models/layout';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { DashboardContent } from '@/components/dashboard/DashboardContent';
import { demoReportResponse } from '@/data/demoReport';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

// 定义标签页类型
interface TabItem {
  id: string;
  title: string;
  fileId: string;
  reportId: string;
}

export function DashboardPage() {
  const [fileSystemItems, setFileSystemItems] =
    useState<FileSystemItem[]>(demoFileSystemData);
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);
  const [dashboardData, setDashboardData] = useState<ReportResponse | null>(
    null
  );

  // 标签页相关状态
  const [openTabs, setOpenTabs] = useState<TabItem[]>([]);
  const [activeTabId, setActiveTabId] = useState<string | null>(null);

  const [layout, setLayout] = useState<Layout | null>(null);

  // 添加导航栏显示控制状态
  const [navbarVisible, setNavbarVisible] = useState(true);
  const [navbarWidth, setNavbarWidth] = useState(256); // 默认宽度为256px

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

  // 打开报表标签页
  const openReportTab = (item: FileSystemItem) => {
    // 检查是否已经打开
    const existingTabIndex = openTabs.findIndex(
      (tab) => tab.fileId === item.id
    );

    if (existingTabIndex !== -1) {
      // 已经打开，激活该标签页
      setActiveTabId(openTabs[existingTabIndex].id);
    } else {
      // 没有打开，创建新标签页
      const newTab: TabItem = {
        id: `tab-${Date.now()}`, // 生成唯一ID
        title: item.name,
        fileId: item.id,
        reportId:
          'file' === item.type ? item.reportId : (item as any).referenceTo,
      };

      setOpenTabs([...openTabs, newTab]);
      setActiveTabId(newTab.id);
    }
  };

  // 关闭标签页
  const closeTab = (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止冒泡，避免触发标签切换

    // 找到要关闭的标签索引
    const tabIndex = openTabs.findIndex((tab) => tab.id === tabId);
    if (tabIndex === -1) return;

    // 创建新的标签数组（移除要关闭的标签）
    const newTabs = openTabs.filter((tab) => tab.id !== tabId);
    setOpenTabs(newTabs);

    // 如果关闭的是当前标签，则激活其他标签
    if (tabId === activeTabId) {
      if (newTabs.length > 0) {
        // 激活相邻标签（优先右侧，其次左侧）
        const newActiveIndex = Math.min(tabIndex, newTabs.length - 1);
        setActiveTabId(newTabs[newActiveIndex].id);
      } else {
        setActiveTabId(null);
      }
    }
  };

  // 处理选择文件系统项目
  const handleSelectItem = (item: FileSystemItem) => {
    setSelectedItem(item);
    // 如果选择的是文件，将其报表ID设置到store中（保留原功能）
    if (item.type === 'file') {
      setDashboardId(item.reportId);
    }
  };

  // 处理双击文件系统项目
  const handleItemDoubleClick = (item: FileSystemItem) => {
    if (item.type === 'file' || item.type === 'reference') {
      openReportTab(item);
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
            onItemDoubleClick={handleItemDoubleClick}
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
        <div className='flex-1 w-0 min-w-0 overflow-hidden flex flex-col'>
          {/* 标签页栏 */}
          {openTabs.length > 0 && (
            <div className='border-b bg-muted/30'>
              <div className='flex overflow-x-auto'>
                {openTabs.map((tab) => (
                  <div
                    key={tab.id}
                    className={cn(
                      'flex items-center px-4 py-2 cursor-pointer border-r border-border relative min-w-[150px] max-w-[200px]',
                      tab.id === activeTabId
                        ? 'bg-background'
                        : 'bg-muted/50 hover:bg-muted'
                    )}
                    onClick={() => setActiveTabId(tab.id)}
                  >
                    <div className='truncate flex-1'>{tab.title}</div>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-4 w-4 ml-2 opacity-60 hover:opacity-100'
                      onClick={(e) => closeTab(tab.id, e)}
                    >
                      <X size={14} />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 标签内容区 */}
          <div className='flex-1 overflow-auto'>
            {openTabs.length > 0 && activeTabId ? (
              <div className='h-full'>
                {openTabs.map((tab) => (
                  <div
                    key={tab.id}
                    className={cn(
                      'h-full',
                      tab.id === activeTabId ? 'block' : 'hidden'
                    )}
                  >
                    <DashboardContent
                      title={demoReportResponse.title}
                      description={demoReportResponse?.description || ''}
                      parameters={demoReportResponse?.parameters || []}
                      dataSources={demoReportResponse?.dataSources || []}
                      layout={demoReportResponse?.layout || []}
                      handleQuerySubmit={handleQuerySubmit}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <div className='flex items-center justify-center h-full text-muted-foreground'>
                双击文件或引用打开报表
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
