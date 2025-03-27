// 定义布局项的接口
interface LayoutItem {
  id: string;
  title: string;
  width: number; // 横向跨列数
  height: number; // 纵向跨行数
  x: number; // 起始列位置
  y: number; // 起始行位置
}

// 定义布局行的接口
interface LayoutRow {
  id: string;
  cells: LayoutItem[];
}

// 定义整体布局的接口
interface Layout {
  columns: number; // 总列数
  rows: number; // 总行数
  items: LayoutItem[]; // 所有图表项
}

export type { Layout, LayoutRow, LayoutItem };
