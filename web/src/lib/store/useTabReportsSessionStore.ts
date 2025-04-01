import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

import type { Report } from '@/types';

// 定义 store 的状态类型
interface TabReportsState {
  // 设置报表
  tabReports: Record<string, Report>;
  getReport: (tabId: string) => Report | undefined;
  setReport: (tabId: string, report: Report) => void;
  removeReport: (tabId: string) => void;

  // 清除
  clear: () => void;
}

// 创建 Zustand Store
export const useTabReportsSessionStore = create<TabReportsState>()(
  persist(
    (set, get) => ({
      tabReports: {},

      getReport: (tabId: string) => {
        const { tabReports } = get();
        return tabReports[tabId];
      },

      setReport: (tabId: string, report: Report) =>
        set((state) => ({
          tabReports: { ...state.tabReports, [tabId]: report },
        })),

      removeReport: (tabId: string) =>
        set((state) => {
          const { [tabId]: _, ...rest } = state.tabReports;
          return { tabReports: rest };
        }),

      clear: () => set({ tabReports: {} }),
    }),
    {
      name: 'reports-session-storage', // sessionStorage 中的 key 名称
      storage: createJSONStorage(() => sessionStorage), // 使用 sessionStorage 进行存储
      partialize: (state) => ({
        tabReports: state.tabReports,
      }),
    }
  )
);
