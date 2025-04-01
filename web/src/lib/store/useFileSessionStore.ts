import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// 定义 store 的状态类型
interface TabFilesState {
  // 操作方法
  tabIdFiles: Record<string, Record<string, File>>;
  getTabIdFiles: (tabId: string) => Record<string, File>;
  setTabIdFiles: (tabId: string, files: Record<string, File>) => void;
}

// 创建 Zustand Store
export const useTabFilesStore = create<TabFilesState>()(
  persist(
    (set, get) => ({
      tabIdFiles: {},

      getTabIdFiles: (tabId: string) => {
        return get().tabIdFiles[tabId];
      },

      setTabIdFiles: (tabId: string, files: Record<string, File>) => {
        set((state) => ({
          tabIdFiles: { ...state.tabIdFiles, [tabId]: files },
        }));
      },
    }),
    {
      name: 'tabIdFiles-session-storage', // localStorage 中的 key 名称
      storage: createJSONStorage(() => sessionStorage), // 使用 localStorage 进行存储
      partialize: (state) => ({
        tabIdFiles: state.tabIdFiles,
      }),
    }
  )
);
