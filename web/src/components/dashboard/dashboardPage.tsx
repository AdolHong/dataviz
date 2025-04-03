import { Button } from '@/components/ui/button';
import { useState, useEffect, memo, useCallback, useMemo } from 'react';
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
import { type TabDetail } from '@/lib/store/useTabsSessionStore';
import { toast } from 'sonner';
import type { FileCache } from '@/lib/store/useFileSessionStore';
import { useTabFilesStore } from '@/lib/store/useFileSessionStore';
import { useTabParamValuesStore } from '@/lib/store/useParamValuesStore';
import { queryApi } from '@/api/query';
import { replaceParametersInCode } from '@/utils/parser';
import { useTabQueryStatusStore } from '@/lib/store/useTabQueryStatusStore';
import {
  type QueryStatus,
  DataSourceStatus,
} from '@/lib/store/useTabQueryStatusStore';
import { shallow } from '@tanstack/react-router';

export function DashboardPage() {
  const [report, setReport] = useState<Report | null>(null);

  const [navbarVisible, setNavbarVisible] = useState(true);
  const [navbarWidth, setNavbarWidth] = useState(256); // 默认宽度为256px

  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [currentEditReport, setCurrentEditReport] = useState<Report | null>(
    null
  );

  const activeTabId = useTabsSessionStore((state) => state.activeTabId);
  const openTabs = useTabsSessionStore((state) => state.tabs);

  const setActiveTabId = useTabsSessionStore((state) => state.setActiveTabId);

  // tabs相关函数
  const findTabsByFileId = useTabsSessionStore(
    (state) => state.findTabsByFileId
  );
  const setCachedTab = useTabsSessionStore((state) => state.setCachedTab);
  const removeCachedTab = useTabsSessionStore((state) => state.removeCachedTab);
  const getCachedTab = useTabsSessionStore((state) => state.getCachedTab);

  const setCachedReport = useTabReportsSessionStore((state) => state.setReport);
  const removeCachedReport = useTabReportsSessionStore(
    (state) => state.removeReport
  );

  const removeTabIdParamValues = useTabParamValuesStore(
    (state) => state.removeTabIdParamValues
  );

  const clearQueryByTabId = useTabQueryStatusStore(
    (state) => state.clearQueryByTabId
  );

  console.info('hi, dashboardPage');

  // 初始化
  useEffect(() => {
    // 如果sesion storage中有活动标签，尝试加载其报表数据
    if (!activeTabId) {
      return;
    }

    const activeTab = getCachedTab(activeTabId);
    if (!activeTab) {
      return;
    }

    // 若有tab记录， 重新查询report
    loadReportForTab(activeTab);
  }, []);

  // 切换tab时
  useEffect(() => {
    console.info('hi, dashboardPage, activeTabId', activeTabId);

    if (activeTabId) {
      const activeTab = getCachedTab(activeTabId);
      if (activeTab) {
        loadReportForTab(activeTab);
      }
    }
  }, [activeTabId]);

  // 为标签加载报表数据的函数
  const loadReportForTab = (tab: TabDetail) => {
    reportApi
      .getReportByReportId(tab.reportId)
      .then((report) => {
        setReport(report);
        setCachedReport(tab.tabId, report);
      })
      .catch((err) => {
        console.error('加载报表失败:', err);
      });
  };

  // 打开报表标签页 - 修改为使用 store
  const openReportTab = (item: FileSystemItem) => {
    // 检查是否已经打开
    const tabs = findTabsByFileId(item.id);

    if (tabs && tabs.length > 0) {
      // 已经打开，激活该标签页
      setActiveTabId(tabs[0].tabId);
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
      setCachedTab(newTab.tabId, newTab);
      // 获取该标签对应的报表数据
      if (newTab.reportId) {
        loadReportForTab(newTab);
      }
    }
  };

  // 关闭标签页 - 使用 store 的 removeTab
  const closeTab = (tabId: string) => {
    // 删除tab
    removeCachedTab(tabId);

    // 删除tab对应的报表
    removeCachedReport(tabId);

    // 删除tab对应的参数值
    removeTabIdParamValues(tabId);

    // 删除tab对应的查询状态
    clearQueryByTabId(tabId);

    // console.log('删除tab之后, tabIdFiles', tabIdFiles);
    // console.log('删除tab之后, tabIdParamValues', tabIdParamValues);
    // console.log('删除tab之后, tabQueryStatus', tabQueryStatus);
  };

  // 处理编辑报表
  const handleEditReport = (report: Report | null) => {
    if (report) {
      setCurrentEditReport(report);
      setIsEditModalOpen(true);
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

    if (currentEditReport) {
      const updatedReport = {
        ...currentEditReport,
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
      setReport(updatedReport);

      //更新tabReports

      setCachedReport(activeTabId, updatedReport);
      setCurrentEditReport(null);
    }
  };

  // fileexplorer: 双击文件或引用
  const handleDoubleClickFileItem = useCallback((item: FileSystemItem) => {
    if (item.id === activeTabId) {
      return;
    }
    // 这里可以添加其他逻辑，例如打开文件或引用
    if (item.type === 'file' || item.type === 'reference') {
      openReportTab(item);
    }
  }, []);

  // fileexplorer: 重命名文件或引用
  const handleRenameItem = useCallback((item: FileSystemItem) => {
    const tabs = findTabsByFileId(item.id);
    tabs.forEach((tab) => {
      setCachedTab(tab.tabId, {
        ...tab,
        title: item.name,
      });
    });
  }, []);

  // fileexplorer: 删除文件
  const handleDeleteItem = useCallback((item: FileSystemItem) => {
    const tabs = findTabsByFileId(item.id);
    tabs.forEach((tab) => {
      removeCachedTab(tab.tabId);
    });
  }, []);

  const handleFileSystemChange = useCallback(
    (oldItems: FileSystemItem[], newItems: FileSystemItem[]) => {
      fsApi.saveFileSystemChanges(oldItems, newItems);
    },
    []
  );

  // tabsArea: 使用 useCallback 优化 onToggleNavbarVisible
  const handleToggleNavbarVisible = useCallback(() => {
    setNavbarVisible((prev) => !prev);
  }, []);

  // tabsArea: 使用 useCallback 优化 onCloseTab
  const handleCloseTab = useCallback((tabId: string) => {
    closeTab(tabId);
  }, []);

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
            onDoubleClick={handleDoubleClickFileItem}
            useFileSystemChangeEffect={handleFileSystemChange}
            useRenameItemEffect={handleRenameItem}
            useDeleteItemEffect={handleDeleteItem}
          />
        </div>

        {/* 右侧内容区 */}
        <div className='flex-1 w-0 min-w-0 overflow-hidden flex flex-col'>
          {/* 标签页栏 */}
          <TabsArea
            navbarVisible={navbarVisible}
            onToggleNavbarVisible={handleToggleNavbarVisible}
            onCloseTab={handleCloseTab}
          />

          {/* 标签内容区 */}
          <div className='flex-1 overflow-auto'>
            {Object.values(openTabs).length > 0 && activeTabId ? (
              <div className='h-full'>
                {/* 为每个报表渲染内容组件 */}
                {/* 展示区域 */}
                <div className='flex-1 overflow-auto'>
                  <div className='container max-w-full py-6 px-4 md:px-8 space-y-6'>
                    {/* 参数区域 */}
                    <div className='space-y-2'>
                      {report && (
                        <ParameterQueryArea
                          report={report}
                          parameters={report.parameters || []}
                          dataSources={report.dataSources || []}
                          onEditReport={() => handleEditReport(report)}
                        />
                      )}
                    </div>

                    {/* 展示区域 */}
                    {report?.layout && report.layout.items.length > 0 && (
                      <LayoutGrid layout={report.layout} />
                    )}
                  </div>
                </div>
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
      {report && (
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

// 标签栏组件
interface TabsAreaProps {
  navbarVisible: boolean;
  onToggleNavbarVisible: () => void;
  onCloseTab: (tabId: string) => void;
}

// 标签栏组件
const TabsArea = memo(
  ({ navbarVisible, onToggleNavbarVisible, onCloseTab }: TabsAreaProps) => {
    const openTabs = useTabsSessionStore((state) => state.tabs);
    const removeCachedTab = useTabsSessionStore(
      (state) => state.removeCachedTab
    );
    const activeTabId = useTabsSessionStore((state) => state.activeTabId);
    const setActiveTabId = useTabsSessionStore((state) => state.setActiveTabId);

    console.info('hi, tabsArea, openTabs', openTabs);

    return (
      <div className='border-b bg-muted/30'>
        <div className='flex overflow-x-auto items-center'>
          {/* 导航栏切换按钮 */}
          <div className='flex items-center border-r border-border px-2'>
            <Button
              variant='ghost'
              size='icon'
              className='h-8 w-8 rounded-full'
              onClick={onToggleNavbarVisible}
            >
              {navbarVisible ? (
                <ChevronLeft size={16} />
              ) : (
                <ChevronRight size={16} />
              )}
            </Button>
          </div>

          {/* 标签页 - 使用 store 中的 openTabs */}
          <>
            {openTabs &&
              Object.values(openTabs).map((tab) => (
                <div
                  key={tab.tabId}
                  className={`flex items-center px-4 py-2 cursor-pointer border-r border-border relative min-w-[150px] max-w-[200px] ${
                    tab.tabId === activeTabId
                      ? 'bg-background'
                      : 'bg-muted/50 hover:bg-muted'
                  }`}
                  onClick={() => {
                    if (tab.tabId != activeTabId) {
                      setActiveTabId(tab.tabId);
                    }
                  }}
                >
                  <div className='truncate flex-1'>{tab.title}</div>
                  <Button
                    variant='ghost'
                    size='icon'
                    className='h-4 w-4 ml-2 opacity-60 hover:opacity-100'
                    onClick={() => {
                      removeCachedTab(tab.tabId);
                      if (onCloseTab) {
                        onCloseTab(tab.tabId);
                      }
                    }}
                  >
                    <X size={14} />
                  </Button>
                </div>
              ))}
          </>
        </div>
      </div>
    );
  }
);
