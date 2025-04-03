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
  getCachedTab: (tabId: string) => TabDetail | undefined;
  setCachedTab: (tabId: string, tab: TabDetail) => void;
  findTabsByFileId: (fileId: string) => TabDetail[];
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
      activeTabId: '',
      getCachedTab: (tabId: string) => get().tabs[tabId],
      setCachedTab: (tabId: string, tab: TabDetail) =>
        set((state) => ({
          tabs: { ...state.tabs, [tabId]: tab },
          activeTabId: tab.tabId,
        })),

      findTabsByFileId: (fileId: string) =>
        Object.values(get().tabs).filter((tab) => tab.fileId === fileId),

      removeCachedTab: (tabId: string) =>
        set((state) => {
          // 若不包含tabId, 则直接返回
          if (!state.tabs[tabId]) {
            return { tabs: state.tabs };
          }

          const oldTabs = { ...state.tabs };
          delete oldTabs[tabId];

          // 若删除的是正在激活的tab
          if (tabId === state.activeTabId) {
            const keysList = Object.keys(oldTabs);
            const minTabId =
              keysList.length === 0
                ? ''
                : keysList.reduce((a, b) => (a < b ? a : b));
            console.info('pardon, 删除激活', oldTabs);
            return { tabs: oldTabs, activeTabId: minTabId };
          } else {
            console.info('pardon, 删除未激活', oldTabs);
            return { tabs: oldTabs };
          }
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
