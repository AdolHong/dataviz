import { Button } from '@/components/ui/button';
import { useState, useEffect } from 'react';
import { FileExplorer } from '@/components/dashboard/FileExplorer';
import type {
  FileItem,
  FileSystemItem,
  ReferenceItem,
} from '@/types/models/fileSystem';
import type { Artifact, DataSource, Parameter, Report } from '@/types';
import type { Layout } from '@/types/models/layout';
import { ChevronLeft, ChevronRight, X, Edit } from 'lucide-react';
import { fsApi } from '@/api/fs';
import EditModal from '@/components/edit/EditModal';
import { reportApi } from '@/api/report';
import { useTabsSessionStore } from '@/lib/store/useTabsSessionStore';
import { useTabReportsSessionStore } from '@/lib/store/useTabReportsSessionStore';
import { useSessionIdStore } from '@/lib/store/useSessionIdStore';

import { ParameterQueryArea } from '@/components/dashboard/ParameterQueryArea';
import { LayoutGrid } from '@/components/dashboard/LayoutGrid';

export function DashboardPage() {
  const [fileSystemItems, setFileSystemItems] = useState<FileSystemItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);

  // 其他状态保持不变
  const [navbarVisible, setNavbarVisible] = useState(true);
  const [navbarWidth, setNavbarWidth] = useState(256); // 默认宽度为256px

  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [currentEditReport, setCurrentEditReport] = useState<Report | null>(
    null
  );
  const [currentEditingTabId, setCurrentEditingTabId] = useState<string | null>(
    null
  );

  // 使用 store 来管理标签页
  const {
    tabs: openTabs,
    activeTabId,
    addTab,
    removeTab,
    setActiveTab,
  } = useTabsSessionStore();

  const { tabReports, getReport, setReport, removeReport } =
    useTabReportsSessionStore();

  const { getSessionId } = useSessionIdStore();

  // 初始化
  // 初始化
  useEffect(() => {
    fsApi.getAllItems().then((items) => {
      setFileSystemItems(items);
    });

    // 如果有活动标签，尝试加载其报表数据
    if (activeTabId) {
      const activeTab = openTabs.find((tab) => tab.tabId === activeTabId);
      if (activeTab && !getReport(activeTab.tabId)) {
        loadReportForTab(activeTab);
      }
    }
  }, []);

  // 加载了文件系统，就更新navbar宽度
  useEffect(() => {
    // todo: 没有考虑文件夹的长度
    if (selectedItem && selectedItem.name) {
      // 计算一个基础宽度，每个字符大约10px，最小256px，最大400px
      const nameLength = selectedItem.name.length;
      const calculatedWidth = Math.min(Math.max(256, nameLength * 10), 400);
      setNavbarWidth(calculatedWidth);
    }
  }, [fileSystemItems]);

  // 为标签加载报表数据的函数
  const loadReportForTab = (tab: (typeof openTabs)[0]) => {
    reportApi
      .getReportByFileId(tab.fileId)
      .then((report) => {
        setReport(tab.tabId, report);
      })
      .catch((err) => {
        console.error('加载报表失败:', err);
      });
  };

  // 打开报表标签页 - 修改为使用 store
  const openReportTab = (item: FileSystemItem) => {
    // 检查是否已经打开
    const existingTab = openTabs.find((tab) => tab.fileId === item.id);

    if (existingTab) {
      // 已经打开，激活该标签页
      setActiveTab(existingTab.tabId);
    } else {
      // 没有打开，创建新标签页
      const newTab = {
        tabId: `tab-${Date.now()}`, // 生成唯一ID
        title: item.name,
        fileId: item.id,
        reportId:
          item.type === 'file'
            ? (item as FileItem).reportId
            : (item as ReferenceItem).reportId,
      };

      // 新增tab
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

    // 删除tab
    removeTab(tabId);

    // 删除tab对应的报表
    removeReport(tabId);
  };

  // 修改handleQuerySubmit函数，接收文件参数为对象
  const handleQuerySubmit = (
    values: Record<string, any>,
    files?: Record<string, File[]>
  ) => {
    console.log('查询参数:', values);
    console.log('上传文件:', files);
  };

  // 处理编辑报表
  const handleEditReport = (report: Report | undefined, tabId: string) => {
    if (report) {
      setCurrentEditReport(report);
      setIsEditModalOpen(true);
      // 保存当前编辑的标签ID，以便保存时更新正确的标签数据
      setCurrentEditingTabId(tabId);
    }
  };

  // 处理保存报表
  const handleSaveReport = (
    title: string,
    description: string,
    createdAt: string,
    updatedAt: string,
    parameters: Parameter[],
    artifacts: Artifact[],
    dataSources: DataSource[],
    layout: Layout
  ) => {
    setIsEditModalOpen(false);

    // 更新当前标签的报表数据
    if (currentEditingTabId) {
      const currentReport = getReport(currentEditingTabId);
      if (currentReport) {
        const updatedReport = {
          ...currentReport,
          title,
          description,
          createdAt,
          updatedAt,
          parameters,
          artifacts,
          dataSources,
          layout,
        };

        console.log('更新报表', updatedReport);
        // api: 更新报表
        reportApi.updateReport(updatedReport.id, updatedReport);

        // 同时更新其他状态
        setReport(currentEditingTabId, updatedReport); //更新tabReports
        setCurrentEditingTabId(null); //清空当前编辑的标签ID
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
            onSelectItem={setSelectedItem}
            onItemDoubleClick={(item) => {
              if (item.type === 'file' || item.type === 'reference') {
                console.log('打开报表', item);
                openReportTab(item);
              }
            }}
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
                  onClick={() => setNavbarVisible(!navbarVisible)}
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
                  key={tab.tabId}
                  className={`flex items-center px-4 py-2 cursor-pointer border-r border-border relative min-w-[150px] max-w-[200px] ${
                    tab.tabId === activeTabId
                      ? 'bg-background'
                      : 'bg-muted/50 hover:bg-muted'
                  }`}
                  onClick={() => setActiveTab(tab.tabId)}
                >
                  <div className='truncate flex-1'>{tab.title}</div>
                  <Button
                    variant='ghost'
                    size='icon'
                    className='h-4 w-4 ml-2 opacity-60 hover:opacity-100'
                    onClick={(e) => closeTab(tab.tabId, e)}
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
                  const reportData = tabReports[tab.tabId];
                  return (
                    <div
                      key={tab.tabId}
                      className={`h-full ${tab.tabId === activeTabId ? 'block' : 'hidden'}`}
                    >
                      {/* 添加编辑按钮 */}
                      <div className='absolute top-4 right-4 z-10'>
                        <Button
                          variant='outline'
                          size='icon'
                          onClick={() =>
                            handleEditReport(tabReports[tab.tabId], tab.tabId)
                          }
                        >
                          <Edit className='h-4 w-4' />
                        </Button>
                      </div>

                      {/* 展示区域 */}
                      <div className='flex-1 overflow-auto'>
                        <div className='container max-w-full py-6 px-4 md:px-8 space-y-6'>
                          {/* 参数区域 */}
                          <div className='space-y-2'>
                            <ParameterQueryArea
                              parameters={reportData?.parameters || []}
                              dataSources={reportData?.dataSources || []}
                              onSubmit={handleQuerySubmit}
                            />
                          </div>
                          <h1 className='text-2xl font-bold'>
                            {reportData?.title}
                          </h1>
                          {reportData?.description && (
                            <h2 className='text-sm text-muted-foreground'>
                              {reportData.description}
                            </h2>
                          )}

                          {/* 展示区域 */}
                          {reportData?.layout &&
                            reportData.layout.items.length > 0 && (
                              <LayoutGrid layout={reportData.layout} />
                            )}
                        </div>
                      </div>
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
