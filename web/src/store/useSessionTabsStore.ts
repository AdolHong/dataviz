import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface SessionTab {
  id: string;
  name: string;
  description: string;
}

// 创建 Zustand Store
export const useSessionTabsStore = create(
  persist(
    (set, get) => ({
      sessionTabs: {}, // 初始状态为一个空对象

      // 添加或更新用户的 count
      addSessionTab: (sessionTabId: string, sessionTab: SessionTab) =>
        set((state: { sessionTabs: { [x: string]: SessionTab } }) => ({
          sessionTabs: {
            ...state.sessionTabs,
            [sessionTabId]: sessionTab,
          },
        })),

      getSessionTab: (sessionTabId: string) => {
        const tabs = get().sessionTabs as Record<string, SessionTab>;
        return tabs[sessionTabId];
      },

      printSessionTabs: () => {
        console.log(get().sessionTabs);
      },
    }),
    {
      name: 'session-tabs-storage', // localStorage 中的 key 名称
      storage: createJSONStorage(() => localStorage), // 使用 localStorage 进行存储
    }
  )
);
