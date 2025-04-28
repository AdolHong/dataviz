// 使用Zustand创建store (dataSourceDialogStore.ts)
import { create } from 'zustand';

import { type QueryStatus } from '@/lib/store/useQueryStatusStore';
import type { DataSource } from '@/types/models/dataSource';

interface DataSourceDialogState {
  isOpen: boolean;
  dataSource: DataSource | null;
  queryStatus: QueryStatus | null;
  openDialog: (dataSource: DataSource, queryStatus: QueryStatus) => void;
  closeDialog: () => void;
}

export const useDataSourceDialogStore = create<DataSourceDialogState>(
  (set) => ({
    isOpen: false,
    dataSource: null,
    queryStatus: null,
    openDialog: (dataSource, queryStatus) =>
      set({
        isOpen: true,
        dataSource,
        queryStatus,
      }),
    closeDialog: () =>
      set({ isOpen: false, dataSource: null, queryStatus: null }),
  })
);
