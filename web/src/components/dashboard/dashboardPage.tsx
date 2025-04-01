import { Button } from '@/components/ui/button';
import { useState, useEffect } from 'react';
import { FileExplorer } from '@/components/dashboard/FileExplorer';
import type { FileSystemItem } from '@/types/models/fileSystem';
import type { ReportResponse } from '@/types';
import type { Layout } from '@/types/models/layout';
import { ChevronLeft, ChevronRight, X, Edit } from 'lucide-react';
import { demoReportResponse } from '@/data/demoReport';
import { fsApi } from '@/api/fs';
import { DashboardContent } from '@/components/dashboard/DashboardContent';
import EditModal from '@/components/edit/EditModal';
import { reportApi } from '@/api/report';
import { useSessionTabsStore } from '@/store/useSessionTabsStore';

// 这个接口定义可以删除，因为我们已经在 store 中定义了 DashboardTab
// interface TabItem { ... }

export function DashboardPage() {
  const [fileSystemItems, setFileSystemItems] = useState<FileSystemItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);
  const [dashboardData, setDashboardData] = useState<ReportResponse | null>(
    null
  );

  // 使用 store 来管理标签页
  const {
    tabs: openTabs,
    activeTabId,
    tabReports,
    setTabs,
    addTab,
    removeTab,
    setActiveTab,
    setTabReport,
  } = useSessionTabsStore();

  // 删除原来的标签状态管理
  // const [openTabs, setOpenTabs] = useState<TabItem[]>([]);
  // const [activeTabId, setActiveTabId] = useState<string | null>(null);
  // const [tabReports, setTabReports] = useState<Record<string, ReportResponse>>({});

  // 其他状态保持不变
  const [navbarVisible, setNavbarVisible] = useState(true);
  const [navbarWidth, setNavbarWidth] = useState(256); // 默认宽度为256px

  const [queryResults, setQueryResults] = useState<Record<string, any> | null>(
    null
  );
  const [layout, setLayout] = useState<Layout | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [currentEditReport, setCurrentEditReport] =
    useState<ReportResponse | null>(null);
  const [currentEditingTabId, setCurrentEditingTabId] = useState<string | null>(
    null
  );

  // 初始化
  useEffect(() => {
    fsApi.getAllItems().then((items) => {
      setFileSystemItems(items);
    });

    // 如果有活动标签，尝试加载其报表数据
    if (activeTabId) {
      const activeTab = openTabs.find((tab) => tab.id === activeTabId);
      if (activeTab && !tabReports[activeTabId]) {
        loadReportForTab(activeTab);
      }
    }
  }, []);

  // 为标签加载报表数据的函数
  const loadReportForTab = (tab: (typeof openTabs)[0]) => {
    reportApi
      .getReportByFileId(tab.fileId)
      .then((report) => {
        setTabReport(tab.id, report);
      })
      .catch((err) => {
        console.error('加载报表失败:', err);
        // 加载失败时使用演示数据
        setTabReport(tab.id, demoReportResponse);
      });
  };

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

  // 打开报表标签页 - 修改为使用 store
  const openReportTab = (item: FileSystemItem) => {
    // 检查是否已经打开
    const existingTab = openTabs.find((tab) => tab.fileId === item.id);

    if (existingTab) {
      // 已经打开，激活该标签页
      setActiveTab(existingTab.id);
    } else {
      // 没有打开，创建新标签页
      const newTab = {
        id: `tab-${Date.now()}`, // 生成唯一ID
        title: item.name,
        fileId: item.id,
        reportId:
          'file' === item.type ? item.reportId : (item as any).referenceTo,
      };

      addTab(newTab);

      // 获取该标签对应的报表数据
      if (newTab.reportId) {
        loadReportForTab(newTab);
      }
    }
  };

  // 关闭标签页 - 使用 store 的 removeTab
  const closeTab = (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // 阻止冒泡，避免触发标签切换
    removeTab(tabId);
  };

  // 处理选择文件系统项目
  const handleSelectItem = (item: FileSystemItem) => {
    setSelectedItem(item);
    // 如果选择的是文件，将其报表ID保存到状态中
    if (item.type === 'file') {
      setDashboardData(demoReportResponse); // 使用演示数据
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

  // 处理编辑报表
  const handleEditReport = (report: ReportResponse, tabId: string) => {
    setCurrentEditReport(report);
    setIsEditModalOpen(true);
    // 保存当前编辑的标签ID，以便保存时更新正确的标签数据
    setCurrentEditingTabId(tabId);
  };

  // 处理保存报表
  const handleSaveReport = (
    title: string,
    description: string,
    parameters: any[],
    artifacts: any[],
    dataSources: any[],
    layout: Layout
  ) => {
    // 这里可以添加保存报表的逻辑
    console.log('保存报表', {
      title,
      description,
      parameters,
      artifacts,
      dataSources,
      layout,
    });
    setIsEditModalOpen(false);

    // 更新当前标签的报表数据
    if (currentEditingTabId) {
      const currentReport = tabReports[currentEditingTabId];
      if (currentReport) {
        const updatedReport = {
          ...currentReport,
          title,
          description,
          parameters,
          artifacts,
          dataSources,
          layout,
        };

        // 使用 store 的方法更新报表数据
        setTabReport(currentEditingTabId, updatedReport);

        // 同时更新其他状态
        setDashboardData(updatedReport);
        setLayout(layout);
        setCurrentEditingTabId(null);
      }
    }
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
            fsItems={fileSystemItems}
            setFsItems={(items) => {
              fsApi.saveFileSystemChanges(fileSystemItems, items);
              setFileSystemItems(items);
            }}
            onSelectItem={handleSelectItem}
            onItemDoubleClick={handleItemDoubleClick}
          />
        </div>

        {/* 右侧内容区 */}
        <div className='flex-1 w-0 min-w-0 overflow-hidden flex flex-col'>
          {/* 标签页栏 */}
          <div className='border-b bg-muted/30'>
            <div className='flex overflow-x-auto items-center'>
              {/* 导航栏切换按钮 */}
              <div className='flex items-center border-r border-border px-2'>
                <Button
                  variant='ghost'
                  size='icon'
                  className='h-8 w-8 rounded-full'
                  onClick={toggleNavbar}
                >
                  {navbarVisible ? (
                    <ChevronLeft size={16} />
                  ) : (
                    <ChevronRight size={16} />
                  )}
                </Button>
              </div>

              {/* 标签页 - 使用 store 中的 openTabs */}
              {openTabs.map((tab) => (
                <div
                  key={tab.id}
                  className={`flex items-center px-4 py-2 cursor-pointer border-r border-border relative min-w-[150px] max-w-[200px] ${
                    tab.id === activeTabId
                      ? 'bg-background'
                      : 'bg-muted/50 hover:bg-muted'
                  }`}
                  onClick={() => setActiveTab(tab.id)}
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

          {/* 标签内容区 */}
          <div className='flex-1 overflow-auto'>
            {openTabs.length > 0 && activeTabId ? (
              <div className='h-full'>
                {/* 为每个报表渲染内容组件 */}
                {openTabs.map((tab) => {
                  const reportData = tabReports[tab.id] || demoReportResponse;
                  return (
                    <div
                      key={tab.id}
                      className={`h-full ${tab.id === activeTabId ? 'block' : 'hidden'}`}
                    >
                      {/* 添加编辑按钮 */}
                      <div className='absolute top-4 right-4 z-10'>
                        <Button
                          variant='outline'
                          size='icon'
                          onClick={() => handleEditReport(reportData, tab.id)}
                        >
                          <Edit className='h-4 w-4' />
                        </Button>
                      </div>
                      {/* 使用 DashboardContent 组件替换原有内容 */}
                      <DashboardContent
                        title={reportData.title || '报表'}
                        description={reportData.description || ''}
                        parameters={reportData.parameters || []}
                        dataSources={reportData.dataSources || []}
                        layout={
                          reportData.layout || {
                            items: [],
                            columns: 1,
                            rows: 1,
                          }
                        }
                        handleQuerySubmit={handleQuerySubmit}
                      />
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className='flex items-center justify-center h-full text-muted-foreground'>
                双击文件或引用打开报表
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 添加 EditModal 组件 */}
      {currentEditReport && (
        <EditModal
          open={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          report={currentEditReport}
          handleSave={handleSaveReport}
        />
      )}
    </div>
  );
}
