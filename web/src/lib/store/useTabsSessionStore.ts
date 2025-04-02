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
  getTab: (tabId: string) => TabDetail | undefined;
  setTab: (tabId: string, tab: TabDetail) => void;
  findTabsByFileId: (fileId: string) => TabDetail[];
  removeTab: (tabId: string) => void;

  // 设置激活标签
  activeTabId: string;
  setActiveTab: (tabId: string | null) => void;
  getActiveTab: () => TabDetail | undefined;

  // 清除
  clear: () => void;
}

// 创建 Zustand Store
export const useTabsSessionStore = create<TabsState>()(
  persist(
    (set, get) => ({
      tabs: {},
      activeTabId: '',
      getTab: (tabId: string) => get().tabs[tabId],
      setTab: (tabId: string, tab: TabDetail) =>
        set((state) => ({
          tabs: { ...state.tabs, [tabId]: tab },
          activeTabId: tab.tabId,
        })),

      findTabsByFileId: (fileId: string) =>
        Object.values(get().tabs).filter((tab) => tab.fileId === fileId),

      removeTab: (tabId: string) =>
        set((state) => {
          const oldTabs = state.tabs;
          delete oldTabs[tabId];

          // 若删除的是正在激活的tab
          if (tabId === state.activeTabId) {
            const keysList = Object.keys(oldTabs);
            const minTabId =
              keysList.length === 0
                ? null
                : keysList.reduce((a, b) => (a < b ? a : b));

            return { tabs: oldTabs, activeTabId: minTabId || '' };
          } else {
            return { tabs: oldTabs };
          }
        }),

      setActiveTab: (tabId: string | null) => set({ activeTabId: tabId || '' }),

      getActiveTab: () => {
        const { tabs, activeTabId } = get();
        return activeTabId ? tabs[activeTabId] : undefined;
      },

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
