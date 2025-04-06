import { Button } from '@/components/ui/button';
import { useState, useEffect, memo, useCallback, useMemo, useRef } from 'react';
import { FileExplorer } from '@/components/dashboard/FileExplorer';
import type {
  FileItem,
  FileSystemItem,
  ReferenceItem,
} from '@/types/models/fileSystem';
import type { Artifact, DataSource, Parameter, Report } from '@/types';
import type { Layout } from '@/types/models/layout';
import { ChevronLeft, ChevronRight, User, X, LogOut } from 'lucide-react';
import { fsApi } from '@/api/fs';
import EditModal from '@/components/edit/EditModal';
import { reportApi } from '@/api/report';
import {
  useTabsSessionStore,
  type TabDetail,
} from '@/lib/store/useTabsSessionStore';

import { ParameterQueryArea } from '@/components/dashboard/ParameterQueryArea';
import { LayoutGrid } from '@/components/dashboard/LayoutGrid';
import { useQueryStatusStore } from '@/lib/store/useQueryStatusStore';
import { useParamValuesStore } from '@/lib/store/useParamValuesStore';
import { useTabFilesStore } from '@/lib/store/useFileSessionStore';
import { useNavigate } from '@tanstack/react-router';

// 为标签加载报表数据的函数
const loadReportForTab = async (tab: TabDetail) => {
  const report = await reportApi.getReportByReportId(tab.reportId);
  return report;
};

export function DashboardPage() {
  const [report, setReport] = useState<Report | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [navbarVisible, setNavbarVisible] = useState(true);

  console.info('hi, dashboardPage');

  // zustand 相关取值
  const activeTabId = useTabsSessionStore((state) => state.activeTabId);

  // zustand 相关函数
  const setActiveTabId = useTabsSessionStore((state) => state.setActiveTabId);
  const findTabsByFileId = useTabsSessionStore(
    (state) => state.findTabsByFileId
  );
  const findTabsByReportId = useTabsSessionStore(
    (state) => state.findTabsByReportId
  );
  const setCachedTab = useTabsSessionStore((state) => state.setCachedTab);
  const removeCachedTab = useTabsSessionStore((state) => state.removeCachedTab);
  const getCachedTab = useTabsSessionStore((state) => state.getCachedTab);

  // 初始化(用useRef, 开发模式也仅渲染一次)
  const effectCalled = useRef(false);
  useEffect(() => {
    if (effectCalled.current) return;
    effectCalled.current = true;
    // 如果session storage中有活动标签，尝试加载其报表数据
    if (!activeTabId) {
      return;
    }

    const activeTab = getCachedTab(activeTabId);
    if (!activeTab) {
      return;
    }

    // 加载报表
    loadReportForTab(activeTab).then((report) => {
      // 若有tab记录， 重新查询report
      setReport(report);
    });
  }, []);

  // 打开报表标签页 - 修改为使用 store
  const doubleClickedReportTab = async (item: FileSystemItem) => {
    // 检查是否已经打开
    const tabs = findTabsByFileId(item.id);
    let targetTab = null;

    if (tabs && tabs.length > 0) {
      targetTab = tabs[0];
    } else {
      // 没有打开，创建新标签页
      targetTab = {
        tabId: `tab-${Date.now()}`, // 生成唯一ID
        title: item.name,
        fileId: item.id,
        reportId:
          item.type === 'file'
            ? (item as FileItem).reportId
            : (item as ReferenceItem).reportId,
      };

      // setCachedTab(targetTab.tabId, targetTab); // PS： 两次渲染，导致report数据重复加载(AI不要删我注释)
    }
    // 获取该标签对应的报表数据
    const report = await loadReportForTab(targetTab);
    setReport(report);
    setActiveTabId(targetTab.tabId);

    if (tabs.length === 0) {
      // 新增tab
      setCachedTab(targetTab.tabId, targetTab); // PS： 1次渲染，导致report数据重复加载(AI不要删我注释)
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

    if (report) {
      const updatedReport = {
        ...report,
        title,
        description,
        createdAt,
        updatedAt,
        parameters,
        artifacts,
        dataSources,
        layout,
      };

      // api: 更新报表
      reportApi.updateReport(updatedReport.id, updatedReport);

      // 同时更新其他状态
      setReport(updatedReport);
    }
  };

  // fileexplorer: 双击文件或引用
  const handleDoubleClickFileItem = useCallback((item: FileSystemItem) => {
    // 若activeTabId对的应的tab记录中，fileId与item.id相同，则不进行操作
    const activeTab = getCachedTab(activeTabId);
    if (item.id === activeTab?.fileId) {
      return;
    }

    // 双击文件或引用
    if (item.type === 'file' || item.type === 'reference') {
      doubleClickedReportTab(item);
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
    if (item.type === 'file' || item.type === 'reference') {
      const tabs = findTabsByReportId(item.reportId);
      tabs.forEach((tab) => {
        removeCachedTab(tab.tabId);
      });
    }
  }, []);

  // fileexplorer: 文件系统保存变更
  const handleFileSystemChange = useCallback(
    (oldItems: FileSystemItem[], newItems: FileSystemItem[]) => {
      fsApi.saveFileSystemChanges(oldItems, newItems);
    },
    []
  );

  // tabsArea: 使用 useCallback 优化 onToggleNavbarVisible
  const handleToggleNavbarVisible = useCallback(() => {
    setNavbarVisible((prev) => !prev);
  }, [report]);

  // textArea: 使用 useCallback 优化 setReport
  const handleSetReport = useCallback(
    (report: Report) => {
      setReport(report);
    },
    [report]
  );

  // query area: 使用 useMemo 优化参数
  const memoizedParameters = useMemo(() => report?.parameters, [report]);
  const memoizedDataSources = useMemo(() => report?.dataSources, [report]);
  const memoizedArtifacts = useMemo(() => report?.artifacts, [report]);
  const memoizedOnEditReport = useCallback(() => {
    if (report) {
      setIsEditModalOpen(true);
    }
  }, [report]);
  const memoizedReportId = useMemo(() => report?.id || '', [report]);
  const memoizedReportUpdatedAt = useMemo(
    () => report?.updatedAt || '',
    [report]
  );
  const memoizedActiveTabId = useMemo(() => activeTabId || '', [report]);

  const navigate = useNavigate();
  const username = sessionStorage.getItem('auth-username') || 'UnknownUser';

  const handleLogout = () => {
    // 清除sessionStorage中的token和username
    sessionStorage.removeItem('auth-token');
    sessionStorage.removeItem('auth-username');

    // 重定向到登录页面
    navigate({ to: '/login' });
  };

  return (
    <div className='flex flex-col h-screen relative'>
      {/* 顶部Header */}
      <div className='border-b bg-background flex items-center justify-between h-14 px-4'>
        {/* 左侧Logo */}
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

        {/* 右侧用户信息 */}
        <div className='flex items-center space-x-4'>
          <div className='flex items-center space-x-2'>
            <User size={16} className='text-gray-600' />
            <span className='text-sm font-medium'>{username}</span>
          </div>

          <Button
            variant='ghost'
            size='icon'
            onClick={handleLogout}
            className='hover:bg-red-50'
            title='注销'
          >
            <LogOut size={16} className='text-red-500' />
          </Button>
        </div>
      </div>

      <div className='flex flex-1 overflow-hidden'>
        {/* 左侧导航栏 */}
        <div
          className='border-r bg-background overflow-auto transition-all duration-300 ease-in-out flex-shrink-0'
          style={{
            width: navbarVisible ? '256px' : '0px',
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
            setReport={handleSetReport}
            navbarVisible={navbarVisible}
            onToggleNavbarVisible={handleToggleNavbarVisible}
          />

          {/* 标签内容区 */}
          <div className='flex-1 overflow-auto'>
            {activeTabId ? (
              <div className='h-full'>
                {/* 为每个报表渲染内容组件 */}
                {/* 展示区域 */}
                <div key={activeTabId} className='flex-1 overflow-auto'>
                  <div className='container max-w-full py-6 px-4 md:px-8 space-y-6'>
                    {/* 参数区域 */}
                    <div className='space-y-2'>
                      {report && (
                        <ParameterQueryArea
                          activeTabId={memoizedActiveTabId}
                          reportId={memoizedReportId}
                          reportUpdatedAt={memoizedReportUpdatedAt}
                          parameters={memoizedParameters}
                          dataSources={memoizedDataSources}
                          artifacts={memoizedArtifacts}
                          onEditReport={memoizedOnEditReport}
                        />
                      )}
                    </div>

                    {/* 展示区域 */}
                    {report?.layout && report.layout.items.length > 0 && (
                      <LayoutGrid
                        report={report}
                        activeTabId={memoizedActiveTabId}
                      />
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className='flex items-center justify-center h-full text-muted-foreground'></div>
            )}
          </div>
        </div>
      </div>

      {/* 添加 EditModal 组件 */}
      {report && (
        <EditModal
          open={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          report={report}
          handleSave={handleSaveReport}
        />
      )}
    </div>
  );
}

// 标签栏组件
interface TabsAreaProps {
  setReport: (report: Report) => void;
  navbarVisible: boolean;
  onToggleNavbarVisible: () => void;
}

// 标签栏组件
const TabsArea = memo(
  ({ setReport, navbarVisible, onToggleNavbarVisible }: TabsAreaProps) => {
    if (!setReport) {
      return <div>setReport is not defined</div>;
    }

    const openTabs = useTabsSessionStore((state) => state.tabs);
    const storeTabsOrder = useTabsSessionStore((state) => state.tabsOrder);
    const activeTabId = useTabsSessionStore((state) => state.activeTabId);
    const setActiveTabId = useTabsSessionStore((state) => state.setActiveTabId);
    const removeCachedTab = useTabsSessionStore(
      (state) => state.removeCachedTab
    );
    const updateTabsOrder = useTabsSessionStore(
      (state) => state.updateTabsOrder
    );

    const clearTabIdParamValues = useParamValuesStore(
      (state) => state.clearNonWhitelistedTabs
    );
    const clearQueryStatusByTabId = useQueryStatusStore(
      (state) => state.clearNonWhitelistedTabs
    );
    const clearFilesByTabId = useTabFilesStore(
      (state) => state.clearNonWhitelistedTabs
    );

    // 用于拖拽功能的状态
    const [draggedItem, setDraggedItem] = useState<string | null>(null);
    const [localTabsOrder, setLocalTabsOrder] = useState<string[]>([]);

    // 初始化本地标签顺序，使用store中的值
    useEffect(() => {
      if (storeTabsOrder.length > 0) {
        setLocalTabsOrder(storeTabsOrder);
      } else if (Object.keys(openTabs).length > 0) {
        // 如果store中没有顺序，但有tabs，则使用tabs的顺序
        const newOrder = Object.values(openTabs).map((tab) => tab.tabId);
        setLocalTabsOrder(newOrder);
        updateTabsOrder(newOrder);
      }
    }, [openTabs, storeTabsOrder]);

    // 加载tab对应的报表
    const loadTabReport = async (targetTab: TabDetail) => {
      // 设置激活tab
      const report = await loadReportForTab(targetTab);
      setReport(report);

      // 更新激活id
      setActiveTabId(targetTab.tabId);
    };

    useEffect(() => {
      // 若openTabs中不存在activeTabId，则选择第一个tab激活
      if (Object.values(openTabs).every((tab) => tab.tabId !== activeTabId)) {
        const leftTabs = Object.values(openTabs).filter(
          (t: TabDetail) => t.tabId !== activeTabId
        );
        if (leftTabs.length > 0) {
          // 获取该标签对应的报表数据
          const targetTab = leftTabs[0];
          loadTabReport(targetTab);
        } else {
          setActiveTabId('');
        }
      }

      // // QueryArea: 仅保留openTabs
      clearTabIdParamValues(Object.keys(openTabs));
      clearFilesByTabId(Object.keys(openTabs));

      // // QueryStatus: 仅保留openTabs
      clearQueryStatusByTabId(Object.keys(openTabs));
    }, [openTabs]);

    // 拖拽事件处理函数
    const handleDragStart = (
      tabId: string,
      e: React.DragEvent<HTMLDivElement>
    ) => {
      setDraggedItem(tabId);
      // 设置拖拽图像（可选）
      if (e.dataTransfer && e.target instanceof HTMLElement) {
        // 创建半透明拖拽效果
        e.dataTransfer.effectAllowed = 'move';
        // 设置光标位置
        e.dataTransfer.setDragImage(e.target, 20, 20);
      }
    };

    const handleDragOver = (
      e: React.DragEvent<HTMLDivElement>,
      targetTabId: string
    ) => {
      e.preventDefault();
      if (draggedItem && draggedItem !== targetTabId) {
        const currentTabsOrder = [...localTabsOrder];
        const draggedIndex = currentTabsOrder.indexOf(draggedItem);
        const targetIndex = currentTabsOrder.indexOf(targetTabId);

        if (draggedIndex !== -1 && targetIndex !== -1) {
          // 从当前位置移除拖动的标签
          currentTabsOrder.splice(draggedIndex, 1);
          // 插入到目标位置
          currentTabsOrder.splice(targetIndex, 0, draggedItem);

          setLocalTabsOrder(currentTabsOrder);
        }
      }
    };

    const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (e.currentTarget) {
        e.currentTarget.classList.add('bg-blue-100', 'dark:bg-blue-900/20');
      }
    };

    const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (e.currentTarget) {
        e.currentTarget.classList.remove('bg-blue-100', 'dark:bg-blue-900/20');
      }
    };

    const handleDragEnd = (e: React.DragEvent<HTMLDivElement>) => {
      if (e.currentTarget) {
        e.currentTarget.classList.remove('bg-blue-100', 'dark:bg-blue-900/20');
      }
      // 持久化到store
      if (draggedItem) {
        updateTabsOrder(localTabsOrder);
      }
      setDraggedItem(null);
    };

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

          {/* 标签页 - 使用 store 中的 tabsOrder */}
          <>
            {localTabsOrder.length > 0 &&
              localTabsOrder.map((tabId) => {
                const tab = openTabs[tabId];
                if (!tab) return null;

                return (
                  <div
                    key={tab.tabId}
                    className={`flex items-center px-4 py-2 cursor-pointer border-r border-border relative min-w-[150px] max-w-[200px] ${
                      tab.tabId === activeTabId
                        ? 'bg-background'
                        : 'bg-muted/50 hover:bg-muted'
                    } ${draggedItem === tab.tabId ? 'opacity-50' : ''}`}
                    onClick={async () => {
                      if (tab.tabId !== activeTabId) {
                        loadTabReport(tab);
                      }
                    }}
                    draggable
                    onDragStart={(e) => handleDragStart(tab.tabId, e)}
                    onDragOver={(e) => handleDragOver(e, tab.tabId)}
                    onDragEnd={handleDragEnd}
                    onDragEnter={handleDragEnter}
                    onDragLeave={handleDragLeave}
                    style={{
                      cursor: 'grab',
                      transition: 'all 0.2s ease-in-out',
                      transform:
                        draggedItem === tab.tabId ? 'scale(0.95)' : 'scale(1)',
                    }}
                  >
                    <div className='truncate flex-1'>{tab.title}</div>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-6 w-6 ml-2 opacity-60 hover:opacity-100'
                      onClick={async (e) => {
                        e.stopPropagation();
                        //删除tab:  remove操作的同时也会更新activeTabId
                        removeCachedTab(tab.tabId);
                        // 从本地标签顺序中移除（store中已通过removeCachedTab移除）
                        setLocalTabsOrder((prev) =>
                          prev.filter((id) => id !== tab.tabId)
                        );
                      }}
                    >
                      <X size={14} />
                    </Button>
                  </div>
                );
              })}
          </>
        </div>
      </div>
    );
  }
);
