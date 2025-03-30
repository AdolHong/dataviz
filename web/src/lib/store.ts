import { create } from 'zustand';

interface DashboardState {
  dashboardId: string | null;
  dashboardParameters: any[];
  dashboardVisualizations: any[];
  dashboardSqlCode: string;

  setDashboardId: (id: string) => void;
  setDashboardParameters: (parameters: any[]) => void;
  setDashboardVisualizations: (visualizations: any[]) => void;
  setDashboardSqlCode: (code: string) => void;
}

export const useStore = create<DashboardState>((set) => ({
  dashboardId: null,
  dashboardParameters: [],
  dashboardVisualizations: [],
  dashboardSqlCode: '',

  setDashboardId: (id) => set({ dashboardId: id }),
  setDashboardParameters: (parameters) =>
    set({ dashboardParameters: parameters }),
  setDashboardVisualizations: (visualizations) =>
    set({ dashboardVisualizations: visualizations }),
  setDashboardSqlCode: (code) => set({ dashboardSqlCode: code }),
}));
