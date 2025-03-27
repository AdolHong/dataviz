// 定义布局项的接口
interface LayoutItem {
  id: string;
  title: string;
  width: number; // 以列数为单位
}

// 定义布局行的接口
interface LayoutRow {
  id: string;
  cells: LayoutItem[];
}

// 定义整体布局的接口
interface Layout {
  columns: number; // 总列数
  rows: LayoutRow[];
}

export type { Layout, LayoutRow, LayoutItem };
