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
  tabs: TabDetail[];
  addTab: (tab: TabDetail) => void;
  removeTab: (tabId: string) => void;

  // 设置激活标签
  activeTabId: string | null;
  setActiveTab: (tabId: string | null) => void;
  getActiveTab: () => TabDetail | undefined;

  // 清除
  clear: () => void;
}

// 创建 Zustand Store
export const useTabsSessionStore = create<TabsState>()(
  persist(
    (set, get) => ({
      tabs: [],
      activeTabId: null,

      addTab: (tab: TabDetail) =>
        set((state) => ({
          tabs: [...state.tabs, tab],
          activeTabId: tab.tabId,
        })),

      removeTab: (tabId: string) =>
        set((state) => {
          const newTabs = state.tabs.filter((tab) => tab.tabId !== tabId);

          // 如果删除的是当前活动标签，需要设置新的活动标签
          let newActiveTabId = state.activeTabId;
          if (tabId === state.activeTabId) {
            const tabIndex = state.tabs.findIndex((tab) => tab.tabId === tabId);
            if (newTabs.length > 0) {
              // 选择相邻标签（优先右侧，其次左侧）
              const newActiveIndex = Math.min(tabIndex, newTabs.length - 1);
              newActiveTabId = newTabs[newActiveIndex].tabId;
            } else {
              newActiveTabId = null;
            }
          }

          return { tabs: newTabs, activeTabId: newActiveTabId };
        }),

      setActiveTab: (tabId: string | null) => set({ activeTabId: tabId }),

      getActiveTab: () => {
        const { tabs, activeTabId } = get();
        return tabs.find((tab) => tab.tabId === activeTabId);
      },

      clear: () => set({ tabs: [], activeTabId: null }),
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
