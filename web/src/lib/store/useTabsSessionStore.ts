import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// 改进标签页类型定义，匹配我们实际需要
interface TabDetail {
  tabId: string;
  title: string;
  fileId: string;
  reportId: string;
}

// 定义 store 的状态类型
interface TabsState {
  // 操作方法
  tabs: Record<string, TabDetail>;
  getTabs: () => TabDetail[];
  getCachedTab: (tabId: string) => TabDetail | undefined;
  setCachedTab: (tabId: string, tab: TabDetail) => void;
  findTabsByFileId: (fileId: string) => TabDetail[];
  findTabsByReportId: (reportId: string) => TabDetail[];
  removeCachedTab: (tabId: string) => void;

  // 设置激活标签
  activeTabId: string;
  setActiveTabId: (tabId: string) => void;

  // 清除
  clear: () => void;
}

// 创建 Zustand Store
export const useTabsSessionStore = create<TabsState>()(
  persist(
    (set, get) => ({
      tabs: {},
      getTabs: () => Object.values(get().tabs),
      activeTabId: '',
      getCachedTab: (tabId: string) => get().tabs[tabId],
      setCachedTab: (tabId: string, tab: TabDetail) =>
        set((state) => ({
          tabs: { ...state.tabs, [tabId]: tab },
          activeTabId: tab.tabId,
        })),

      findTabsByFileId: (fileId: string) =>
        Object.values(get().tabs).filter((tab) => tab.fileId === fileId),

      findTabsByReportId: (reportId: string) =>
        Object.values(get().tabs).filter((tab) => tab.reportId === reportId),

      removeCachedTab: (tabId: string) =>
        set((state) => {
          // 若不包含tabId, 则直接返回
          if (!state.tabs[tabId]) {
            return { tabs: state.tabs };
          }

          // 删除tab
          const oldTabs = { ...state.tabs };
          delete oldTabs[tabId];
          return { tabs: oldTabs };
        }),
      setActiveTabId: (tabId: string) => set({ activeTabId: tabId }),

      clear: () => set({ tabs: {}, activeTabId: '' }),
    }),
    {
      name: 'tabs-session-storage', // localStorage 中的 key 名称
      storage: createJSONStorage(() => sessionStorage), // 使用 localStorage 进行存储
      partialize: (state) => ({
        tabs: state.tabs,
        activeTabId: state.activeTabId,
      }),
    }
  )
);
