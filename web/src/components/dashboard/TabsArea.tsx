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

export const TabsArea = memo(({ setReport }: TabsAreaProps) => {
  const openTabs = useTabsSessionStore((state) => state.tabs);
  const activeTabId = useTabsSessionStore((state) => state.activeTabId);
  const setActiveTabId = useTabsSessionStore((state) => state.setActiveTabId);
  const tabsOrder = useTabsSessionStore((state) => state.tabsOrder);

  const loadTabReport = async (targetTab: TabDetail) => {
    const report = await loadReportForTab(targetTab);
    setReport(report);
    setActiveTabId(targetTab.tabId);
  };

  // 初始化: 清楚tabs
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

    // QueryArea: 仅保留openTabs的cached
    const clearTabIdParamValues =
      useParamValuesStore.getState().clearNonWhitelistedTabs;
    const clearFilesByTabId =
      useTabFilesStore.getState().clearNonWhitelistedTabs;
    const clearQueryStatusByTabId =
      useQueryStatusStore.getState().clearNonWhitelistedTabs;
    clearTabIdParamValues(Object.keys(openTabs));
    clearFilesByTabId(Object.keys(openTabs));
    clearQueryStatusByTabId(Object.keys(openTabs));
  }, [openTabs]);

  return (
    <BaseTabsArea
      tabs={Object.values(tabsOrder).map((tabId) => ({
        tabId: tabId,
        tabName: openTabs[tabId].title,
      }))}
      activeTabId={activeTabId}
      onTabClick={(tabId) => {
        const targetTab = openTabs[tabId];
        if (targetTab) {
          loadTabReport(targetTab);
        }
      }}
      onTabClose={(tabId) => {
        const removeCachedTab = useTabsSessionStore.getState().removeCachedTab;
        removeCachedTab(tabId);
      }}
      onTabOrderChange={(updatedTabs) => {
        const updateTabsOrder = useTabsSessionStore.getState().updateTabsOrder;
        updateTabsOrder(updatedTabs.map((tab) => tab.tabId));
      }}
    />
  );
});
