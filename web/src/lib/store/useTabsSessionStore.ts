import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// 改进标签页类型定义，匹配我们实际需要
export interface TabDetail {
  tabId: string;
  title: string;
  fileId: string;
  reportId: string;
}

// 定义 store 的状态类型
interface TabsState {
  // 操作方法
  tabs: Record<string, TabDetail>;
  tabsOrder: string[]; // 添加 tabsOrder 存储tab顺序
  getTabs: () => TabDetail[];
  getCachedTab: (tabId: string) => TabDetail | undefined;
  setCachedTab: (tabId: string, tab: TabDetail) => void;
  findTabsByFileId: (fileId: string) => TabDetail[];
  findTabsByReportId: (reportId: string) => TabDetail[];
  removeCachedTab: (tabId: string) => void;
  updateTabsOrder: (newOrder: string[]) => void; // 添加更新顺序的方法

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
      tabsOrder: [], // 初始化为空数组
      getTabs: () => Object.values(get().tabs),
      activeTabId: '',
      getCachedTab: (tabId: string) => get().tabs[tabId],
      setCachedTab: (tabId: string, tab: TabDetail) =>
        set((state) => {
          // 如果是新标签，添加到tabsOrder末尾
          const newTabsOrder = [...state.tabsOrder];
          if (!state.tabs[tabId]) {
            newTabsOrder.push(tabId);
          }
          return {
            tabs: { ...state.tabs, [tabId]: tab },
            tabsOrder: newTabsOrder,
            activeTabId: tab.tabId,
          };
        }),

      findTabsByFileId: (fileId: string) =>
        Object.values(get().tabs).filter((tab) => tab.fileId === fileId),

      findTabsByReportId: (reportId: string) =>
        Object.values(get().tabs).filter((tab) => tab.reportId === reportId),

      removeCachedTab: (tabId: string) =>
        set((state) => {
          // 若不包含tabId, 则直接返回
          if (!state.tabs[tabId]) {
            return { tabs: state.tabs, tabsOrder: state.tabsOrder };
          }

          // 删除tab
          const oldTabs = { ...state.tabs };
          delete oldTabs[tabId];

          // 从tabsOrder中移除
          const newTabsOrder = state.tabsOrder.filter((id) => id !== tabId);

          return { tabs: oldTabs, tabsOrder: newTabsOrder };
        }),

      updateTabsOrder: (newOrder: string[]) => set({ tabsOrder: newOrder }),

      setActiveTabId: (tabId: string) => set({ activeTabId: tabId }),

      clear: () => set({ tabs: {}, tabsOrder: [], activeTabId: '' }),
    }),
    {
      name: 'tabs-session-storage', // localStorage 中的 key 名称
      storage: createJSONStorage(() => sessionStorage), // 使用 localStorage 进行存储
      partialize: (state) => ({
        tabs: state.tabs,
        tabsOrder: state.tabsOrder,
        activeTabId: state.activeTabId,
      }),
    }
  )
);
