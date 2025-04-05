import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface FileCache {
  fileName: string;
  fileSize: number;
  fileType: string;
  fileContent: string;
}

// 定义 store 的状态类型
interface ParamValuesState {
  // 操作方法
  tabIdParamValues: Record<string, Record<string, any>>;

  getTabIdParamValues: (tabId: string) => Record<string, any>;
  setTabIdParamValues: (
    tabId: string,
    paramValues: Record<string, any>
  ) => void;

  clearParamValuesByTabId: (tabId: string) => void;
}

// 创建 Zustand Store
export const useParamValuesStore = create<ParamValuesState>()(
  persist(
    (set, get) => ({
      tabIdParamValues: {},

      getTabIdParamValues: (tabId: string) => {
        if (!get().tabIdParamValues[tabId]) {
          set((state) => ({
            tabIdParamValues: { ...state.tabIdParamValues, [tabId]: {} },
          }));
        }
        return get().tabIdParamValues[tabId];
      },

      setTabIdParamValues: (
        tabId: string,
        paramValues: Record<string, any>
      ) => {
        set((state) => ({
          tabIdParamValues: { ...state.tabIdParamValues, [tabId]: paramValues },
        }));
      },

      clearParamValuesByTabId: (tabId: string) => {
        const oldTabIdParamValues = { ...get().tabIdParamValues };
        delete oldTabIdParamValues[tabId];
        set({ tabIdParamValues: oldTabIdParamValues });
      },
    }),
    {
      name: 'tabIdParamValues-session-storage', // sessionStorage 中的 key 名称
      storage: createJSONStorage(() => sessionStorage), // 使用 sessionStorage 进行存储
      partialize: (state) => ({
        tabIdParamValues: state.tabIdParamValues,
      }),
    }
  )
);
