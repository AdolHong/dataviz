import { X } from 'lucide-react';
import { useQueryStatusStore } from '@/lib/store/useQueryStatusStore';
import { useParamValuesStore } from '@/lib/store/useParamValuesStore';
import { useTabFilesStore } from '@/lib/store/useFileSessionStore';
import { useState, useEffect, memo } from 'react';
import { loadReportForTab } from './DashboardPage';
import { Button } from '@/components/ui/button';
import type { Report } from '@/types';

import {
  useTabsSessionStore,
  type TabDetail,
} from '@/lib/store/useTabsSessionStore';

// 标签栏组件
interface TabsAreaProps {
  setReport: (report: Report) => void;
}

// 定义 Tab 接口
interface Tab {
  tabId: string;
  tabName: string;
}

// 定义 BaseTabsArea 的 Props
interface BaseTabsAreaProps {
  // 外部传入的 tabs 数据
  tabs: Tab[];
  // 当前活跃的 tab
  activeTabId?: string;
  // 事件回调
  onTabClick?: (tabId: string) => void;
  onTabClose?: (tabId: string) => void;
  onTabOrderChange?: (tabs: Tab[]) => void;
}

function BaseTabsArea({
  tabs,
  activeTabId,
  onTabClick,
  onTabClose,
  onTabOrderChange,
}: BaseTabsAreaProps) {
  const [draggedItem, setDraggedItem] = useState<string | null>(null);

  const handleDragStart = (
    tabId: string,
    e: React.DragEvent<HTMLDivElement>
  ) => {
    setDraggedItem(tabId);
    if (e.dataTransfer && e.target instanceof HTMLElement) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setDragImage(e.target, 20, 20);
    }
  };

  const handleDragOver = (
    e: React.DragEvent<HTMLDivElement>,
    targetTabId: string
  ) => {
    e.preventDefault();
    if (draggedItem && draggedItem !== targetTabId) {
      const draggedIndex = tabs.findIndex((tab) => tab.tabId === draggedItem);
      const targetIndex = tabs.findIndex((tab) => tab.tabId === targetTabId);

      if (draggedIndex !== -1 && targetIndex !== -1) {
        const updatedTabs = [...tabs];
        const [removedTab] = updatedTabs.splice(draggedIndex, 1);
        updatedTabs.splice(targetIndex, 0, removedTab);

        // 通知外部 tabs 顺序变化
        onTabOrderChange?.(updatedTabs);
      }
    }
  };

  const handleDragEnd = () => {
    setDraggedItem(null);
  };

  return (
    <>
      {tabs.map((tab) => (
        <div
          key={tab.tabId}
          className={`flex items-center px-2 py-1 cursor-pointer border-r border-border relative min-w-[120px] ${
            tab.tabId === activeTabId
              ? 'bg-background'
              : 'bg-muted/50 hover:bg-muted'
          } ${draggedItem === tab.tabId ? 'opacity-50' : ''}`}
          onClick={() => onTabClick?.(tab.tabId)}
          draggable
          onDragStart={(e) => handleDragStart(tab.tabId, e)}
          onDragOver={(e) => handleDragOver(e, tab.tabId)}
          onDragEnd={handleDragEnd}
          style={{
            cursor: 'grab',
            transition: 'all 0.2s ease-in-out',
            transform: draggedItem === tab.tabId ? 'scale(0.95)' : 'scale(1)',
          }}
        >
          <div className='whitespace-nowrap text-xs flex-grow'>
            {tab.tabName}
          </div>
          <Button
            variant='ghost'
            size='icon'
            className='h-5 w-5 ml-1 opacity-60 hover:opacity-100 flex-shrink-0'
            onClick={(e) => {
              e.stopPropagation();
              onTabClose?.(tab.tabId);
            }}
          >
            <X size={12} />
          </Button>
        </div>
      ))}
    </>
  );
}

// 标签栏组件
export const TabsArea = memo(({ setReport }: TabsAreaProps) => {
  if (!setReport) {
    return <div>setReport is not defined</div>;
  }

  const openTabs = useTabsSessionStore((state) => state.tabs);
  const storeTabsOrder = useTabsSessionStore((state) => state.tabsOrder);
  const activeTabId = useTabsSessionStore((state) => state.activeTabId);
  const setActiveTabId = useTabsSessionStore((state) => state.setActiveTabId);
  const removeCachedTab = useTabsSessionStore((state) => state.removeCachedTab);
  const updateTabsOrder = useTabsSessionStore((state) => state.updateTabsOrder);

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
    <>
      {/* 标签页 - 使用 store 中的 tabsOrder */}

      {localTabsOrder.length > 0 &&
        localTabsOrder.map((tabId) => {
          const tab = openTabs[tabId];
          if (!tab) return null;

          return (
            <div
              key={tab.tabId}
              className={`flex items-center px-2 py-1 cursor-pointer border-r border-border relative min-w-[120px] ${
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
              <div className='whitespace-nowrap text-xs flex-grow'>
                {tab.title}
              </div>
              <Button
                variant='ghost'
                size='icon'
                className='h-5 w-5 ml-1 opacity-60 hover:opacity-100 flex-shrink-0'
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
                <X size={12} />
              </Button>
            </div>
          );
        })}
    </>
  );
});
