import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { ChevronsUp, ChevronsDown } from 'lucide-react';
import { toast } from 'sonner';

import type { Layout } from '@/types';
import {
  adjustRows,
  adjustColumns,
  hasOverlappingItems,
  getGridOccupancy,
  removeEmptyRowsAndColumns,
} from '@/types/models/layout';

interface EditLayoutModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (layout: Layout) => void;
  initialLayout?: Layout;
}

export function EditLayoutModal({
  open,
  onClose,
  onSave,
  initialLayout,
}: EditLayoutModalProps) {
  // 默认布局
  const defaultLayout: Layout = {
    columns: 1,
    rows: 1,
    items: [
      {
        id: 'item-1',
        title: '你触发了default layout',
        width: 1,
        height: 1,
        x: 0,
        y: 0,
      },
    ],
  };

  const [layout, setLayout] = useState<Layout>(initialLayout || defaultLayout);

  // 每次 open 或 initialLayout 变化时重新初始化
  useEffect(() => {
    if (open) {
      setLayout(initialLayout || defaultLayout);
    }
  }, [open, initialLayout]);

  // 初始化布局状态

  // 添加状态来跟踪调整中的项目
  const [adjustingItem, setAdjustingItem] = useState<{
    itemId: string;
    targetWidth: number;
    targetHeight: number;
  } | null>(null);

  // 添加拖拽状态
  const [draggedItem, setDraggedItem] = useState<string | null>(null);
  const [dragOverCell, setDragOverCell] = useState<{
    x: number;
    y: number;
  } | null>(null);

  // 处理项目拖拽开始
  const handleItemDragStart = (itemId: string) => {
    setDraggedItem(itemId);
  };

  // 处理项目拖拽结束
  const handleItemDragEnd = () => {
    setDraggedItem(null);
    setDragOverCell(null);
  };

  // 处理单元格拖拽悬停
  const handleCellDragOver = (e: React.DragEvent, x: number, y: number) => {
    e.preventDefault();
    setDragOverCell({ x, y });
  };

  // 处理项目放置
  const handleItemDrop = (e: React.DragEvent, x: number, y: number) => {
    e.preventDefault();
    if (!draggedItem) return;

    // 找到被拖拽的项目
    const item = layout.items.find((item) => item.id === draggedItem);
    if (!item) return;

    // 无论原尺寸多大，都重置为1x1的大小
    const newWidth = 1;
    const newHeight = 1;

    // 检查新位置是否超出边界
    if (x + newWidth > layout.columns || y + newHeight > layout.rows) {
      toast.error('目标位置无法放置该图表');
      return;
    }

    // 更新项目位置和尺寸
    setLayout({
      ...layout,
      items: layout.items.map((i) =>
        i.id === draggedItem
          ? { ...i, x, y, width: newWidth, height: newHeight }
          : i
      ),
    });

    // 重置拖拽状态
    setDraggedItem(null);
    setDragOverCell(null);
  };

  // 处理保存
  const handleSave = () => {
    // 检查项目是否有重叠
    if (hasOverlappingItems(layout)) {
      toast.error('布局中存在重叠的图表，请检查');
      return;
    }

    // 调用方法更新布局
    const updatedLayout = removeEmptyRowsAndColumns(layout);
    setLayout(updatedLayout); // 更新状态

    onSave(updatedLayout);
    onClose();
  };

  // 调整列数
  const handleAdjustColumns = (newColumns: number) => {
    const updatedLayout = adjustColumns(layout, newColumns);
    setLayout(updatedLayout); // 更新状态
  };

  // 调整行数
  const handleAdjustRows = (newRows: number) => {
    const updatedLayout = adjustRows(layout, newRows);
    setLayout(updatedLayout); // 更新状态
  };

  // 添加一个通用的重叠检测函数，供调整手柄使用
  const checkOverlap = (
    itemId: string,
    x: number,
    y: number,
    width: number,
    height: number
  ) => {
    // 创建一个新的网格表示图表的当前占位
    const currentGrid: boolean[][] = Array(layout.rows)
      .fill(false)
      .map(() => Array(layout.columns).fill(false));

    // 获取当前项目
    const item = layout.items.find((item) => item.id === itemId);
    if (!item) return true;

    // 标记当前项目占用的位置
    for (let cy = item.y; cy < item.y + item.height; cy++) {
      for (let cx = item.x; cx < item.x + item.width; cx++) {
        if (cy < layout.rows && cx < layout.columns) {
          currentGrid[cy][cx] = true;
        }
      }
    }

    // 创建一个新的网格表示扩展后要占用的位置
    const newGrid: boolean[][] = Array(layout.rows)
      .fill(false)
      .map(() => Array(layout.columns).fill(false));

    // 标记新尺寸下项目会占用的位置
    for (let ny = y; ny < y + height; ny++) {
      for (let nx = x; nx < x + width; nx++) {
        if (ny < layout.rows && nx < layout.columns) {
          newGrid[ny][nx] = true;
        }
      }
    }

    // 找出新增占用的单元格
    const newCells: { x: number; y: number }[] = [];
    for (let gy = 0; gy < layout.rows; gy++) {
      for (let gx = 0; gx < layout.columns; gx++) {
        if (newGrid[gy][gx] && !currentGrid[gy][gx]) {
          newCells.push({ x: gx, y: gy });
        }
      }
    }

    // 检查新增单元格是否与其他项目重叠
    const otherItems = layout.items.filter((i) => i.id !== itemId);

    for (const cell of newCells) {
      for (const otherItem of otherItems) {
        if (
          cell.x >= otherItem.x &&
          cell.x < otherItem.x + otherItem.width &&
          cell.y >= otherItem.y &&
          cell.y < otherItem.y + otherItem.height
        ) {
          return true; // 有重叠
        }
      }
    }

    return false; // 没有重叠
  };

  // 用于绘制整个网格的函数
  const renderGrid = (layout: Layout) => {
    const grid = getGridOccupancy(layout);
    const gridItems = [];

    // 渲染每个单元格
    for (let y = 0; y < layout.rows; y++) {
      for (let x = 0; x < layout.columns; x++) {
        const itemId = grid[y][x];
        const isDraggedOver =
          dragOverCell && dragOverCell.x === x && dragOverCell.y === y;

        // 检查这个单元格是否是某个项目的左上角
        const isItemStart =
          itemId !== null &&
          layout.items.find(
            (item) => item.id === itemId && item.x === x && item.y === y
          );

        if (isItemStart) {
          // 这是一个项目的起始单元格，我们需要渲染完整的项目
          const item = layout.items.find((item) => item.id === itemId)!;

          // 检查这个单元格是否是被拖拽的项目
          const isDragged = draggedItem === itemId;

          gridItems.push(
            <div
              key={`item-${x}-${y}`}
              className={`border-2 border-dashed rounded-lg p-4 text-center bg-gray-200 relative 
                ${isDragged ? 'opacity-50' : ''}`}
              style={{
                gridColumnStart: x + 1,
                gridColumnEnd: x + item.width + 1,
                gridRowStart: y + 1,
                gridRowEnd: y + item.height + 1,
                zIndex: 1,
              }}
              draggable={true}
              onDragStart={() => handleItemDragStart(item.id)}
              onDragEnd={handleItemDragEnd} // 恢复格子的样式
            >
              <span className='text-center'>{item.title}</span>
              {/* 调整手柄美化版 */}
              <div
                className='absolute right-0 bottom-0 cursor-nwse-resize select-none'
                style={{ zIndex: 10 }}
                onMouseDown={(e) => {
                  e.preventDefault();
                  const startX = e.clientX;
                  const startY = e.clientY;
                  const originalWidth = item.width;
                  const originalHeight = item.height;

                  // 获取网格容器尺寸
                  const gridElement = e.currentTarget.closest('.grid');
                  if (!gridElement) return;

                  // 计算单元格尺寸
                  const gridRect = gridElement.getBoundingClientRect();
                  const cellWidth = gridRect.width / layout.columns;
                  const cellHeight = gridRect.height / layout.rows;

                  const handleMouseMove = (moveEvent: MouseEvent) => {
                    const deltaX = moveEvent.clientX - startX;
                    const deltaY = moveEvent.clientY - startY;

                    // 根据单元格尺寸动态计算增量
                    const deltaColumns = Math.round(deltaX / cellWidth);
                    const deltaRows = Math.round(deltaY / cellHeight);

                    const newWidth = Math.max(1, originalWidth + deltaColumns);
                    const newHeight = Math.max(1, originalHeight + deltaRows);

                    // 检查新尺寸是否超出边界
                    const boundedWidth =
                      item.x + newWidth > layout.columns
                        ? layout.columns - item.x
                        : newWidth;

                    const boundedHeight =
                      item.y + newHeight > layout.rows
                        ? layout.rows - item.y
                        : newHeight;

                    // 检查是否有重叠
                    const isOverlapping = checkOverlap(
                      item.id,
                      item.x,
                      item.y,
                      boundedWidth,
                      boundedHeight
                    );

                    if (!isOverlapping) {
                      // 直接更新布局，而不仅仅是预览状态
                      setLayout({
                        ...layout,
                        items: layout.items.map((i) =>
                          i.id === item.id
                            ? {
                                ...i,
                                width: boundedWidth,
                                height: boundedHeight,
                              }
                            : i
                        ),
                      });
                    }

                    // 仍然更新调整状态，用于显示尺寸信息
                    setAdjustingItem({
                      itemId: item.id,
                      targetWidth: boundedWidth,
                      targetHeight: boundedHeight,
                    });
                  };

                  const handleMouseUp = (upEvent: MouseEvent) => {
                    document.removeEventListener('mousemove', handleMouseMove);
                    document.removeEventListener('mouseup', handleMouseUp);

                    // 在鼠标释放时，最终更新一次布局
                    if (adjustingItem) {
                      const finalWidth = adjustingItem.targetWidth;
                      const finalHeight = adjustingItem.targetHeight;

                      // 检查是否有重叠
                      const isOverlapping = checkOverlap(
                        item.id,
                        item.x,
                        item.y,
                        finalWidth,
                        finalHeight
                      );

                      if (isOverlapping) {
                        toast.error('调整尺寸会与其他图表重叠');

                        // 如果有重叠，恢复原始尺寸
                        setLayout({
                          ...layout,
                          items: layout.items.map((i) =>
                            i.id === item.id
                              ? {
                                  ...i,
                                  width: originalWidth,
                                  height: originalHeight,
                                }
                              : i
                          ),
                        });
                      } else {
                        // 布局已经在 handleMouseMove 中更新了，这里只显示一个成功提示
                        toast.success(
                          `已将图表尺寸调整为 ${finalWidth} x ${finalHeight}`
                        );
                      }
                    }

                    setAdjustingItem(null);
                  };

                  document.addEventListener('mousemove', handleMouseMove);
                  document.addEventListener('mouseup', handleMouseUp);
                }}
              >
                {/* 美化后的调整手柄UI */}
                <div className='relative w-6 h-6 flex items-center justify-center'>
                  <div className='absolute right-0.5 bottom-0.5 w-2 h-2 bg-gray-500 rounded-sm'></div>
                  <div className='absolute right-2.5 bottom-0.5 w-1.5 h-1 bg-gray-400 rounded-sm'></div>
                  <div className='absolute right-0.5 bottom-2.5 w-1 h-1.5 bg-gray-400 rounded-sm'></div>
                </div>
              </div>
            </div>
          );
        } else if (!itemId) {
          // 这是一个空单元格，可以用于拖放目标
          gridItems.push(
            <div
              key={`empty-${x}-${y}`}
              className={`border border-dashed border-gray-300 rounded-lg ${isDraggedOver ? 'bg-blue-100' : ''}`}
              style={{
                gridColumnStart: x + 1,
                gridColumnEnd: x + 2,
                gridRowStart: y + 1,
                gridRowEnd: y + 2,
              }}
              onDragOver={(e) => handleCellDragOver(e, x, y)}
              onDrop={(e) => handleItemDrop(e, x, y)}
            />
          );
        }
        // 被某个大图表占用但不是起始点的单元格不需要渲染
      }
    }

    return gridItems;
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className='max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden'>
        <DialogHeader>
          <DialogTitle>编辑布局</DialogTitle>
        </DialogHeader>

        <div className='flex-1 overflow-y-auto p-4'>
          <div className='space-y-4'>
            {/* 布局 */}
            <div className='border rounded-lg p-4'>
              <div
                className='grid gap-4'
                style={{
                  gridTemplateColumns: `repeat(${layout.columns}, 1fr)`,
                  gridTemplateRows: `repeat(${layout.rows}, 100px)`,
                  position: 'relative',
                }}
              >
                {renderGrid(layout)}
              </div>
            </div>

            {/* 行列调整和导入导出 */}
            <div className='flex justify-between flex-wrap gap-4'>
              <div className='flex-1'></div>
              <div className='flex items-center space-x-8'>
                <div className='flex items-center space-x-4'>
                  <Label htmlFor='columns'>列数:</Label>
                  <div className='flex items-center space-x-1'>
                    <div className='text-xl font-medium'>{layout.columns}</div>
                    <div className='relative flex flex-col items-center'>
                      <div className='flex flex-col -mt-1 space-y-1'>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-4 w-4 rounded-b-none py-0'
                          onClick={() =>
                            handleAdjustColumns(layout.columns + 1)
                          }
                        >
                          <ChevronsUp className='h-3 w-3' />
                        </Button>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-4 w-4 rounded-t-none py-0'
                          onClick={() =>
                            handleAdjustColumns(layout.columns - 1)
                          }
                          disabled={layout.columns <= 1}
                        >
                          <ChevronsDown className='h-3 w-3' />
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className='flex items-center space-x-4'>
                  <Label htmlFor='rows'>行数:</Label>
                  <div className='flex items-center space-x-1'>
                    <div className='text-xl font-medium'>{layout.rows}</div>
                    <div className='relative flex flex-col items-center'>
                      <div className='flex flex-col -mt-1 space-y-1'>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-4 w-4 rounded-b-none py-0'
                          onClick={() => handleAdjustRows(layout.rows + 1)}
                        >
                          <ChevronsUp className='h-3 w-3' />
                        </Button>
                        <Button
                          variant='ghost'
                          size='icon'
                          className='h-4 w-4 rounded-t-none py-0'
                          onClick={() => handleAdjustRows(layout.rows - 1)}
                          disabled={layout.rows <= 1}
                        >
                          <ChevronsDown className='h-3 w-3' />
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
