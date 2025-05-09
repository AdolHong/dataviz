import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface FileCache {
  fileName: string;
  fileSize: number;
  fileType: string;
  fileContent: string;
}

// 定义 store 的状态类型
interface TabFilesState {
  // 操作方法
  tabIdFiles: Record<string, Record<string, FileCache>>;
  getTabIdFiles: (tabId: string) => Record<string, FileCache>;
  setTabIdFiles: (tabId: string, files: Record<string, FileCache>) => void;

  clearFilesByTabId: (tabId: string) => void;
  clearNonWhitelistedTabs: (whitelistedTabIds: string[]) => void;
}

// 创建 Zustand Store
export const useTabFilesStore = create<TabFilesState>()(
  persist(
    (set, get) => ({
      tabIdFiles: {},

      getTabIdFiles: (tabId: string) => {
        if (!get().tabIdFiles[tabId]) {
          set((state) => ({
            tabIdFiles: { ...state.tabIdFiles, [tabId]: {} },
          }));
        }
        return get().tabIdFiles[tabId];
      },

      setTabIdFiles: (tabId: string, files: Record<string, FileCache>) => {
        set((state) => ({
          tabIdFiles: { ...state.tabIdFiles, [tabId]: files },
        }));
      },

      clearFilesByTabId: (tabId: string) => {
        const oldTabIdFiles = { ...get().tabIdFiles };
        delete oldTabIdFiles[tabId];
        set({ tabIdFiles: oldTabIdFiles });
      },

      clearNonWhitelistedTabs: (whitelistedTabIds: string[]) => {
        set((state) => {
          const newTabIdFiles = { ...state.tabIdFiles };

          // 遍历当前所有的tabId
          Object.keys(newTabIdFiles).forEach((tabId) => {
            // 如果当前tabId不在白名单中，则删除
            if (!whitelistedTabIds.includes(tabId)) {
              delete newTabIdFiles[tabId];
            }
          });

          return { tabIdFiles: newTabIdFiles };
        });
      },
    }),

    {
      name: 'tabIdFiles-session-storage', // sessionStorage 中的 key 名称
      storage: createJSONStorage(() => sessionStorage), // 使用 sessionStorage 进行存储
      partialize: (state) => ({
        tabIdFiles: state.tabIdFiles,
      }),
    }
  )
);
