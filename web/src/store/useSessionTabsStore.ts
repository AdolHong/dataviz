import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { ReportResponse } from '@/types';

// 改进标签页类型定义，匹配我们实际需要
interface DashboardTab {
  id: string;
  title: string;
  fileId: string;
  reportId: string;
}

// 定义 store 的状态类型
interface SessionTabsState {
  tabs: DashboardTab[];
  activeTabId: string | null;
  tabReports: Record<string, ReportResponse>;

  // 操作方法
  addTab: (tab: DashboardTab) => void;
  removeTab: (tabId: string) => void;

  // 设置激活标签
  setActiveTab: (tabId: string | null) => void;
  getActiveTab: () => DashboardTab | undefined;

  // 设置报表
  setTabReport: (tabId: string, report: ReportResponse) => void;
  getTabReport: (tabId: string) => ReportResponse | undefined;

  // 清除
  clear: () => void;
}

// 创建 Zustand Store
export const useSessionTabsStore = create<SessionTabsState>()(
  persist(
    (set, get) => ({
      tabs: [],
      activeTabId: null,
      tabReports: {},

      addTab: (tab: DashboardTab) =>
        set((state) => ({
          tabs: [...state.tabs, tab],
          activeTabId: tab.id,
        })),

      removeTab: (tabId: string) =>
        set((state) => {
          const newTabs = state.tabs.filter((tab) => tab.id !== tabId);

          // 如果删除的是当前活动标签，需要设置新的活动标签
          let newActiveTabId = state.activeTabId;
          if (tabId === state.activeTabId) {
            const tabIndex = state.tabs.findIndex((tab) => tab.id === tabId);
            if (newTabs.length > 0) {
              // 选择相邻标签（优先右侧，其次左侧）
              const newActiveIndex = Math.min(tabIndex, newTabs.length - 1);
              newActiveTabId = newTabs[newActiveIndex].id;
            } else {
              newActiveTabId = null;
            }
          }

          return { tabs: newTabs, activeTabId: newActiveTabId };
        }),

      setActiveTab: (tabId: string | null) => set({ activeTabId: tabId }),

      getActiveTab: () => {
        const { tabs, activeTabId } = get();
        return tabs.find((tab) => tab.id === activeTabId);
      },

      setTabReport: (tabId: string, report: ReportResponse) =>
        set((state) => ({
          tabReports: { ...state.tabReports, [tabId]: report },
        })),

      getTabReport: (tabId: string) => {
        return get().tabReports[tabId];
      },

      clear: () => set({ tabs: [], activeTabId: null, tabReports: {} }),
    }),
    {
      name: 'dashboard-tabs-storage', // localStorage 中的 key 名称
      storage: createJSONStorage(() => localStorage), // 使用 localStorage 进行存储
      partialize: (state) => ({
        tabs: state.tabs,
        activeTabId: state.activeTabId,
        // 我们也可以选择不持久化报表数据，以减少存储大小
        // tabReports: state.tabReports
      }),
    }
  )
);
