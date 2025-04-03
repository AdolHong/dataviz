import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface QueryStatus {
  status: DataSourceStatus;
  error?: string;
  rowCount?: number;
  demoData?: string;
}

// 定义 store 的状态类型
interface TabQueryStatusState {
  tabQueryStatus: Record<string, Record<string, QueryStatus>>;
  getQueryStatusByTabId: (tabId: string) => Record<string, QueryStatus>;
  setQueryStatusByTabId: (
    tabId: string,
    status: Record<string, QueryStatus>
  ) => void;

  setQueryStatusByTabIdAndSourceId: (
    tabId: string,
    sourceId: string,
    status: QueryStatus
  ) => void;
  getQueryStatusByTabIdAndSourceId: (
    tabId: string,
    sourceId: string
  ) => QueryStatus;

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

// 创建 Zustand Store
export const useTabQueryStatusStore = create<TabQueryStatusState>()(
  persist(
    (set, get) => ({
      tabQueryStatus: {},

      getQueryStatusByTabId: (tabId: string) => {
        if (!get().tabQueryStatus[tabId]) {
          set((state) => ({
            tabQueryStatus: {
              ...state.tabQueryStatus,
              [tabId]: {},
            },
          }));
        }
        return get().tabQueryStatus[tabId];
      },
      setQueryStatusByTabId: (
        tabId: string,
        status: Record<string, QueryStatus>
      ) => {
        set((state) => ({
          tabQueryStatus: {
            ...state.tabQueryStatus,
            [tabId]: status,
          },
        }));
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

      getQueryStatusByTabIdAndSourceId: (tabId: string, sourceId: string) => {
        if (!get().tabQueryStatus[tabId]) {
          set((state) => ({
            tabQueryStatus: {
              ...state.tabQueryStatus,
              [tabId]: {},
            },
          }));
        }
        return (
          get().tabQueryStatus[tabId][sourceId] || {
            status: DataSourceStatus.INIT,
          }
        );
      },

      setQueryStatusByTabIdAndSourceId: (
        tabId: string,
        sourceId: string,
        status: QueryStatus
      ) => {
        // 如果tabId不存在, 则创建一个空的tabQueryStatus
        if (!get().tabQueryStatus[tabId]) {
          set((state) => ({
            tabQueryStatus: {
              ...state.tabQueryStatus,
              [tabId]: {
                [sourceId]: status,
              },
            },
          }));
          return;
        }
        set((state) => ({
          tabQueryStatus: {
            ...state.tabQueryStatus,
            [tabId]: {
              ...state.tabQueryStatus[tabId],
              [sourceId]: status,
            },
          },
        }));
      },

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
