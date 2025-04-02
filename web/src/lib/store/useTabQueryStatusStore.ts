import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// 定义 store 的状态类型
interface TabQueryStatusState {
  tabQueryStatus: Record<string, Record<string, QueryStatus>>;
  getQueryStatus: (tabId: string, sourceId: string) => QueryStatus;
  setQueryStatus: (
    tabId: string,
    sourceId: string,
    status: QueryStatus
  ) => void;
  getQueryStatusByTabId: (tabId: string) => Record<string, QueryStatus>;
  clearQueryByTabId: (tabId: string) => void;
  clear: () => void;
}

// 定义文件系统中的项目类型：文件夹或文件
export enum DataSourceStatus {
  RUNNING = 'running',
  SCHEDULED = 'scheduled',
  SUCCESS = 'success',
  ERROR = 'error',
  INIT = 'init',
}

export interface QueryStatus {
  status: DataSourceStatus;
  error?: string;
  rowCount?: number;
  demoData?: string;
}

// 创建 Zustand Store
export const useTabQueryStatusStore = create<TabQueryStatusState>()(
  persist(
    (set, get) => ({
      tabQueryStatus: {},

      // 查询状态
      getQueryStatus: (tabId: string, sourceId: string) => {
        const statusDict = get().tabQueryStatus[tabId];
        // 若tabId不存在，则创建一个
        if (!statusDict) {
          const newStatusDict = {
            [sourceId]: {
              status: DataSourceStatus.INIT,
            },
          };
          set((state) => ({
            tabQueryStatus: {
              ...state.tabQueryStatus,
              [tabId]: newStatusDict,
            },
          }));
          return newStatusDict[sourceId];
        } else if (!statusDict[sourceId]) {
          // 若sourceId不存在，则创建一个
          const newStatusDict = {
            ...statusDict,
            [sourceId]: {
              status: DataSourceStatus.INIT,
            },
          };
          set((state) => ({
            tabQueryStatus: {
              ...state.tabQueryStatus,
              [tabId]: newStatusDict,
            },
          }));
          return newStatusDict[sourceId];
        }
        return statusDict[sourceId];
      },

      // 设置查询状态
      setQueryStatus: (
        tabId: string,
        sourceId: string,
        status: QueryStatus
      ) => {
        const statusDict = get().tabQueryStatus[tabId];
        if (!statusDict) {
          const newStatusDict = {
            [sourceId]: status,
          };
          set((state) => ({
            tabQueryStatus: {
              ...state.tabQueryStatus,
              [tabId]: newStatusDict,
            },
          }));
        } else {
          set((state) => ({
            tabQueryStatus: {
              ...state.tabQueryStatus,
              [tabId]: {
                ...statusDict,
                [sourceId]: status,
              },
            },
          }));
        }
      },

      getQueryStatusByTabId: (tabId: string) => {
        return get().tabQueryStatus[tabId];
      },

      // 根据tabId清除所有查询状态
      clearQueryByTabId: (tabId: string) =>
        set((state) => ({
          tabQueryStatus: Object.fromEntries(
            Object.entries(state.tabQueryStatus).filter(
              ([key]) => key !== tabId
            )
          ),
        })),

      // 清除所有查询状态
      clear: () => set({ tabQueryStatus: {} }),
    }),
    {
      name: 'query-status-session-storage', // sessionStorage 中的 key 名称
      storage: createJSONStorage(() => sessionStorage), // 使用 sessionStorage 进行存储
      partialize: (state) => ({
        tabQueryStatus: state.tabQueryStatus,
      }),
    }
  )
);
