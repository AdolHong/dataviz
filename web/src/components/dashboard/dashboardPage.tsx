import { Button } from '@/components/ui/button';
import { useState, useEffect, act } from 'react';
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

export function DashboardPage() {
  const [selectedItem, setSelectedItem] = useState<FileSystemItem | null>(null);
  const [report, setReport] = useState<Report | null>(null);

  const [navbarVisible, setNavbarVisible] = useState(true);
  const [navbarWidth, setNavbarWidth] = useState(256); // 默认宽度为256px

  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [currentEditReport, setCurrentEditReport] = useState<Report | null>(
    null
  );
  const [currentEditingTabId, setCurrentEditingTabId] = useState<string | null>(
    null
  );
  const [isQuerying, setIsQuerying] = useState(false);
  // 使用 store 来管理标签页

  const [statusDict, setStatusDict] = useState<Record<string, QueryStatus>>({});

  const {
    activeTabId,
    setActiveTab,
    getActiveTab,
    findTabsByFileId,
    getTab,
    setTab,
    removeTab: removeCachedTab,
  } = useTabsSessionStore();
  const { getSessionId } = useSessionIdStore();
  const { setReport: setCachedReport, removeReport: removeCachedReport } =
    useTabReportsSessionStore();
  const { removeTabIdFiles, tabIdFiles, setTabIdFiles } = useTabFilesStore();
  const { removeTabIdParamValues, tabIdParamValues, setTabIdParamValues } =
    useTabParamValuesStore();
  const { clearQueryByTabId, tabQueryStatus, setQueryStatus } =
    useTabQueryStatusStore();

  // 初始化
  useEffect(() => {
    // 如果sesion storage中有活动标签，尝试加载其报表数据
    if (!activeTabId) {
      return;
    }

    const activeTab = getTab(activeTabId);
    if (!activeTab) {
      return;
    }

    // 若有tab记录， 重新查询report
    loadReportForTab(activeTab);
  }, []);

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
      setActiveTab(tabs[0].tabId);
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
      setTab(newTab.tabId, newTab);

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
    removeCachedTab(tabId);

    // 删除tab对应的报表
    removeCachedReport(tabId);

    // 删除tab对应的参数值
    removeTabIdParamValues(tabId);

    // 删除tab对应的查询状态
    clearQueryByTabId(tabId);

    console.log('删除tab之后, tabIdFiles', tabIdFiles);
    console.log('删除tab之后, tabIdParamValues', tabIdParamValues);
    console.log('删除tab之后, tabQueryStatus', tabQueryStatus);
  };

  // 修改handleQuerySubmit函数，接收文件参数为对象
  const handleQuerySubmit = async (
    tabId: string,
    values: Record<string, any>,
    files?: Record<string, FileCache>
  ) => {
    // 缓存参数
    setTabIdParamValues(tabId, values);

    // 缓存文件
    setTabIdFiles(tabId, files || {});

    console.log('你点击了查询');
    console.log('files', files);
    console.log('values', values);

    if (report) {
      setIsQuerying(true);
      const promises = report.dataSources
        .filter((dataSource) => dataSource.executor.type === 'sql')
        .map((dataSource) =>
          handleQueryRequest(report, dataSource, values, tabId)
        );
      await Promise.all(promises);
      setIsQuerying(false);

      console.log('查询完成or失败, who knows?');
    }
  };

  const handleQueryRequest = async (
    report: Report,
    dataSource: DataSource,
    values: Record<string, any>,
    tabId: string
  ) => {
    // sessionId + tabId + dataSourceId (标识此处请求是唯一的)
    const uniqueId = getSessionId() + '_' + tabId + '_' + dataSource.id;

    let response = null;
    if (dataSource.executor.type === 'sql') {
      const code = replaceParametersInCode(dataSource.executor.code, values);
      const request = {
        fileId: report.id,
        sourceId: dataSource.id,
        updateTime: report.updatedAt,
        uniqueId: uniqueId,
        paramValues: values,
        code: code,
        dataContent: null,
      };
      response = await queryApi.executeQueryBySourceId(request);
    }

    // 更新查询状态
    if (response.status === 'success') {
      setStatusDict((prev) => ({
        ...prev,
        [dataSource.id]: {
          status: DataSourceStatus.SUCCESS,
        } as QueryStatus,
      }));
      setQueryStatus(tabId, dataSource.id, {
        status: DataSourceStatus.SUCCESS,
      });
    } else {
      setQueryStatus(tabId, dataSource.id, {
        status: DataSourceStatus.ERROR,
      });
    }
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

      console.log('更新报表', updatedReport);
      // api: 更新报表
      reportApi.updateReport(updatedReport.id, updatedReport);

      // 同时更新其他状态
      setReport(updatedReport);

      //更新tabReports

      setCachedReport(activeTabId, updatedReport);
      setCurrentEditingTabId(null); //清空当前编辑的标签ID
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
            onSelectItem={setSelectedItem}
            onItemDoubleClick={(item) => {
              if (item.id === activeTabId) {
                return;
              }
              if (item.type === 'file' || item.type === 'reference') {
                openReportTab(item);
              }
            }}
            useFileSystemChangeEffect={(
              oldItems: FileSystemItem[],
              newItems: FileSystemItem[]
            ) => {
              fsApi.saveFileSystemChanges(oldItems, newItems);
            }}
            useRenameItemEffect={(item) => {
              const tabs = findTabsByFileId(item.id);
              tabs.forEach((tab) => {
                setTab(tab.tabId, {
                  ...tab,
                  title: item.name,
                });
              });
            }}
            useDeleteItemEffect={(item) => {
              const tabs = findTabsByFileId(item.id);
              tabs.forEach((tab) => {
                removeCachedTab(tab.tabId);
              });
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
              <TabsArea
                activeTabId={activeTabId}
                setActiveTab={setActiveTab}
                closeTab={closeTab}
              />
            </div>
          </div>

          {/* 标签内容区 */}
          <div className='flex-1 overflow-auto'>
            {activeTabId ? (
              <div className='h-full'>
                {/* 展示区域 */}
                <div className='flex-1 overflow-auto'>
                  <div className='container max-w-full py-6 px-4 md:px-8 space-y-6'>
                    {/* 参数区域 */}
                    <div className='space-y-2'>
                      <ParameterQueryArea
                        tabId={activeTabId}
                        parameters={report?.parameters || []}
                        dataSources={report?.dataSources || []}
                        isQuerying={isQuerying}
                        statusDict={statusDict}
                        setStatusDict={setStatusDict}
                        onSubmit={(values, files) =>
                          handleQuerySubmit(activeTabId, values, files)
                        }
                        onEditReport={() =>
                          report && handleEditReport(report, activeTabId)
                        }
                      />
                    </div>
                    <h1 className='text-2xl font-bold'>
                      {getActiveTab()?.title}
                    </h1>
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
          report={report}
          handleSave={handleSaveReport}
        />
      )}
    </div>
  );
}

interface TabsAreaProps {
  activeTabId: string;
  setActiveTab: (tabId: string) => void;
  closeTab: (tabId: string, e: React.MouseEvent<Element, MouseEvent>) => void;
}

function TabsArea({ activeTabId, setActiveTab, closeTab }: TabsAreaProps) {
  const { tabs: openTabs } = useTabsSessionStore();

  return (
    /* 标签页 - 使用 store 中的 openTabs */

    <>
      {Object.values(openTabs).map((tab) => (
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
    </>
  );
}
