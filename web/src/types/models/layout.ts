import { toast } from 'sonner';

// 定义布局项的接口
interface LayoutItem {
  id: string; // 自动生成
  title: string;
  width: number; // 横向跨列数
  height: number; // 纵向跨行数
  x: number; // 起始列位置
  y: number; // 起始行位置
}

// 定义整体布局的接口
interface Layout {
  columns: number; // 总列数
  rows: number; // 总行数
  items: LayoutItem[]; // 所有图表项
}

// 计算实际渲染的网格 - 这会创建一个二维数组，表示每个单元格被哪个项目占用
export const getGridOccupancy = (layout: Layout) => {
  // 创建一个二维数组，初始化为null
  const grid: (string | null)[][] = Array(layout.rows)
    .fill(null)
    .map(() => Array(layout.columns).fill(null));

  // 遍历所有项目，填充网格
  layout.items.forEach((item) => {
    for (let y = item.y; y < item.y + item.height; y++) {
      for (let x = item.x; x < item.x + item.width; x++) {
        // 确保在网格范围内
        if (y < layout.rows && x < layout.columns) {
          grid[y][x] = item.id;
        }
      }
    }
  });

  return grid;
};

// 删除多余的空行和空列
export const removeEmptyRowsAndColumns = (layout: Layout): Layout => {
  const nonEmptyRows = new Set<number>();
  const nonEmptyColumns = new Set<number>();

  layout.items.forEach((item) => {
    for (let y = item.y; y < item.y + item.height; y++) {
      nonEmptyRows.add(y);
    }
    for (let x = item.x; x < item.x + item.width; x++) {
      nonEmptyColumns.add(x);
    }
  });

  const newRows = Math.max(...nonEmptyRows) + 1;
  const newColumns = Math.max(...nonEmptyColumns) + 1;

  // 返回新的布局对象
  return {
    ...layout,
    rows: newRows,
    columns: newColumns,
    items: layout.items.filter((item) => {
      return item.x < newColumns && item.y < newRows;
    }),
  };
};

// 调整行数
export const adjustRows = (layout: Layout, newRows: number): Layout => {
  if (newRows < 1) return layout;

  // 检查是否有项目超出新的行数
  const willBeOutOfBounds = layout.items.some(
    (item) => item.y + item.height > newRows
  );

  if (willBeOutOfBounds) {
    toast.error('减少行数会导致某些图表超出边界');
    return layout; // 返回原始布局
  }

  return {
    ...layout,
    rows: newRows,
  };
};

// 调整列数
export const adjustColumns = (layout: Layout, newColumns: number): Layout => {
  if (newColumns < 1) return layout;

  // 检查是否有项目超出新的列数
  const willBeOutOfBounds = layout.items.some(
    (item) => item.x + item.width > newColumns
  );

  if (willBeOutOfBounds) {
    toast.error('减少列数会导致某些图表超出边界');
    return layout; // 返回原始布局
  }

  return {
    ...layout,
    columns: newColumns,
  };
};

// 添加新项目
export const addItem = (layout: Layout, id: string, title: string) => {
  const isEmptyLayout = layout.items.length === 0;

  // 新item, 默认新增一行:  若空，则填充
  const newItem: LayoutItem = {
    id: id,
    title: title,
    width: layout.columns,
    height: 1,
    x: 0,
    y: isEmptyLayout ? 0 : layout.rows,
  };

  return {
    ...layout,
    rows: layout.rows + 1,
    items: [...layout.items, newItem],
  };
};

// 删除项目
export const removeItem = (layout: Layout, itemId: string): Layout => {
  const items = layout.items.filter((item) => item.id !== itemId);
  return {
    ...layout,
    items: items,
  };
};

// 检查是否有项目重叠或超出边界
export const hasOverlappingItems = (layout: Layout) => {
  const grid = getGridOccupancy(layout);
  const itemCounts = new Map<string, number>();

  // 计算每个项目在网格中出现的次数
  for (let y = 0; y < grid.length; y++) {
    for (let x = 0; x < grid[y].length; x++) {
      const itemId = grid[y][x];
      if (itemId) {
        itemCounts.set(itemId, (itemCounts.get(itemId) || 0) + 1);
      }
    }
  }

  // 检查每个项目是否占用了应该占用的单元格数量
  let hasOverlap = false;
  layout.items.forEach((item) => {
    const expectedCells = item.width * item.height;
    const actualCells = itemCounts.get(item.id) || 0;

    if (actualCells < expectedCells) {
      // 项目超出边界
      hasOverlap = true;
    }
  });

  return hasOverlap;
};

// 导出 Layout 类和 LayoutItem 类型
export type { Layout, LayoutItem };
