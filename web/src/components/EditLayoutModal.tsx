import { useState } from 'react';
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { ChevronsUp, ChevronsDown } from 'lucide-react';
import { toast } from "sonner";

import type { Layout, LayoutItem } from '@/types';

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
  initialLayout
}: EditLayoutModalProps) {
  // 默认布局
  const defaultLayout: Layout = {
    columns: 3,
    rows: 4,
    items: [
      { id: 'item-1', title: '销售趋势', width: 1, height: 1, x: 0, y: 0 },
      { id: 'item-2', title: '区域销售占比', width: 1, height: 1, x: 1, y: 0 },
      { id: 'item-3', title: '销售明细数据', width: 1, height: 1, x: 2, y: 0 },
      { id: 'item-4', title: '新增图表1', width: 1, height: 1, x: 0, y: 1 },
      { id: 'item-5', title: '图表4', width: 2, height: 3, x: 1, y: 1 },
      { id: 'item-6', title: '新增图表3', width: 1, height: 1, x: 0, y: 3 },
    ]
  };

  // 初始化布局状态
  const [layout, setLayout] = useState<Layout>(initialLayout || defaultLayout);
  
  // 添加状态来跟踪调整中的项目
  const [adjustingItem, setAdjustingItem] = useState<{
    itemId: string, 
    targetWidth: number,
    targetHeight: number
  } | null>(null);

  // 添加拖拽状态
  const [draggedItem, setDraggedItem] = useState<string | null>(null);
  const [dragOverCell, setDragOverCell] = useState<{x: number, y: number} | null>(null);

  // 计算实际渲染的网格 - 这会创建一个二维数组，表示每个单元格被哪个项目占用
  const getGridOccupancy = () => {
    // 创建一个二维数组，初始化为null
    const grid: (string | null)[][] = Array(layout.rows).fill(null).map(() => 
      Array(layout.columns).fill(null)
    );
    
    // 遍历所有项目，填充网格
    layout.items.forEach(item => {
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

  // 检查是否有项目重叠或超出边界
  const hasOverlappingItems = () => {
    const grid = getGridOccupancy();
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
    layout.items.forEach(item => {
      const expectedCells = item.width * item.height;
      const actualCells = itemCounts.get(item.id) || 0;
      
      if (actualCells < expectedCells) {
        // 项目超出边界
        hasOverlap = true;
      }
    });
    
    return hasOverlap;
  };

  // 添加新项目
  const addItem = () => {
    // 查找第一个可用位置
    const grid = getGridOccupancy();
    let foundPosition = false;
    let newX = 0;
    let newY = 0;
    
    for (let y = 0; y < layout.rows; y++) {
      for (let x = 0; x < layout.columns; x++) {
        if (grid[y][x] === null) {
          newX = x;
          newY = y;
          foundPosition = true;
          break;
        }
      }
      if (foundPosition) break;
    }
    
    // 如果没有可用位置，添加到最后一行
    if (!foundPosition) {
      newY = layout.rows;
      setLayout({
        ...layout,
        rows: layout.rows + 1
      });
    }
    
    const newItem: LayoutItem = {
      id: `item-${Date.now()}`,
      title: '新图表',
      width: 1,
      height: 1,
      x: newX,
      y: newY
    };
    
    setLayout({
      ...layout,
      items: [...layout.items, newItem]
    });
  };

  // 删除项目
  const removeItem = (itemId: string) => {
    setLayout({
      ...layout,
      items: layout.items.filter(item => item.id !== itemId)
    });
  };

  // 调整行数
  const adjustRows = (newRows: number) => {
    if (newRows < 1) return;
    
    // 检查是否有项目超出新的行数
    const willBeOutOfBounds = layout.items.some(item => 
      item.y + item.height > newRows
    );
    
    if (willBeOutOfBounds) {
      toast.error("减少行数会导致某些图表超出边界");
      return;
    }
    
    setLayout({
      ...layout,
      rows: newRows
    });
  };

  // 调整列数
  const adjustColumns = (newColumns: number) => {
    if (newColumns < 1) return;
    
    // 检查是否有项目超出新的列数
    const willBeOutOfBounds = layout.items.some(item => 
      item.x + item.width > newColumns
    );
    
    if (willBeOutOfBounds) {
      toast.error("减少列数会导致某些图表超出边界");
      return;
    }
    
    setLayout({
      ...layout,
      columns: newColumns
    });
  };

  // 处理项目拖拽开始
  const handleItemDragStart = (e: React.DragEvent, itemId: string) => {
    setDraggedItem(itemId);
    e.dataTransfer.setData('text/plain', itemId);
    // 设置拖拽效果
    const dragImage = new Image();
    dragImage.src = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
    e.dataTransfer.setDragImage(dragImage, 0, 0);
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
    const item = layout.items.find(item => item.id === draggedItem);
    if (!item) return;
    
    // 无论原尺寸多大，都重置为1x1的大小
    const newWidth = 1;
    const newHeight = 1;
    
    // 检查新位置是否超出边界
    if (x + newWidth > layout.columns) {
      toast.error("目标位置无法放置该图表");
      setDraggedItem(null);
      setDragOverCell(null);
      return;
    }
    
    if (y + newHeight > layout.rows) {
      toast.error("目标位置无法放置该图表");
      setDraggedItem(null);
      setDragOverCell(null);
      return;
    }
    
    // 检查新位置是否与其他项目重叠
    // 创建一个临时的网格，但排除当前被拖拽项目
    const otherItems = layout.items.filter(i => i.id !== draggedItem);
    const tempGrid: (string | null)[][] = Array(layout.rows).fill(null).map(() => 
      Array(layout.columns).fill(null)
    );
    
    // 填充其他项目到临时网格
    otherItems.forEach(otherItem => {
      for (let iy = otherItem.y; iy < otherItem.y + otherItem.height; iy++) {
        for (let ix = otherItem.x; ix < otherItem.x + otherItem.width; ix++) {
          if (iy < layout.rows && ix < layout.columns) {
            tempGrid[iy][ix] = otherItem.id;
          }
        }
      }
    });
    
    // 检查拖拽项目的新位置是否与其他项目重叠
    if (tempGrid[y][x] !== null) {
      toast.error("该位置已被其他图表占用");
      setDraggedItem(null);
      setDragOverCell(null);
      return;
    }
    
    // 如果拖拽的尺寸和原尺寸不同，显示提示
    if (item.width !== newWidth || item.height !== newHeight) {
      toast.info(`图表尺寸已重置为 1x1`);
    }
    
    // 更新项目位置和尺寸
    setLayout({
      ...layout,
      items: layout.items.map(i => 
        i.id === draggedItem ? { ...i, x, y, width: newWidth, height: newHeight } : i
      )
    });
    
    setDraggedItem(null);
    setDragOverCell(null);
  };

  // 删除多余的空行和空列
  const removeEmptyRowsAndColumns = (layout: Layout): Layout => {
    const nonEmptyRows = new Set<number>();
    const nonEmptyColumns = new Set<number>();

    layout.items.forEach(item => {
      for (let y = item.y; y < item.y + item.height; y++) {
        nonEmptyRows.add(y);
      }
      for (let x = item.x; x < item.x + item.width; x++) {
        nonEmptyColumns.add(x);
      }
    });

    const newRows = Math.max(...nonEmptyRows) + 1;
    const newColumns = Math.max(...nonEmptyColumns) + 1;

    return {
      ...layout,
      rows: newRows,
      columns: newColumns,
      items: layout.items.filter(item => {
        return (
          item.x < newColumns && 
          item.y < newRows
        );
      })
    };
  };

  // 处理保存
  const handleSave = () => {
    // 检查项目是否有重叠
    if (hasOverlappingItems()) {
      toast.error("布局中存在重叠的图表，请检查");
      return;
    }

    // 调用函数并更新layout
    const updatedLayout = removeEmptyRowsAndColumns(layout);
    setLayout(updatedLayout);

    onSave(updatedLayout);
    onClose();
  };

  // 添加一个通用的重叠检测函数，供调整手柄使用
  const checkOverlap = (itemId: string, x: number, y: number, width: number, height: number) => {
    // 创建一个新的网格表示图表的当前占位
    const currentGrid: boolean[][] = Array(layout.rows).fill(false).map(() => 
      Array(layout.columns).fill(false)
    );
    
    // 获取当前项目
    const item = layout.items.find(item => item.id === itemId);
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
    const newGrid: boolean[][] = Array(layout.rows).fill(false).map(() => 
      Array(layout.columns).fill(false)
    );
    
    // 标记新尺寸下项目会占用的位置
    for (let ny = y; ny < y + height; ny++) {
      for (let nx = x; nx < x + width; nx++) {
        if (ny < layout.rows && nx < layout.columns) {
          newGrid[ny][nx] = true;
        }
      }
    }
    
    // 找出新增占用的单元格
    const newCells: {x: number, y: number}[] = [];
    for (let gy = 0; gy < layout.rows; gy++) {
      for (let gx = 0; gx < layout.columns; gx++) {
        if (newGrid[gy][gx] && !currentGrid[gy][gx]) {
          newCells.push({x: gx, y: gy});
        }
      }
    }
    
    // 检查新增单元格是否与其他项目重叠
    const otherItems = layout.items.filter(i => i.id !== itemId);
    
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
  const renderGrid = () => {
    const grid = getGridOccupancy();
    const gridItems = [];
    
    // 渲染每个单元格
    for (let y = 0; y < layout.rows; y++) {
      for (let x = 0; x < layout.columns; x++) {
        const itemId = grid[y][x];
        const isDraggedOver = dragOverCell && dragOverCell.x === x && dragOverCell.y === y;
        
        // 检查这个单元格是否是某个项目的左上角
        const isItemStart = itemId !== null && 
          layout.items.find(item => item.id === itemId && item.x === x && item.y === y);
        
        if (isItemStart) {
          // 这是一个项目的起始单元格，我们需要渲染完整的项目
          const item = layout.items.find(item => item.id === itemId)!;
          
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
                zIndex: 1
              }}
              draggable={true}
              onDragStart={(e) => handleItemDragStart(e, item.id)}
              onDragEnd={handleItemDragEnd}
            >
              <span className="text-center">{item.title}</span>
              
              {/* 如果是正在调整的项目，显示目标尺寸 */}
              {adjustingItem && adjustingItem.itemId === item.id && (
                <div className="absolute inset-0 bg-blue-200 bg-opacity-50 flex items-center justify-center">
                  <div className="bg-white p-2 rounded shadow">
                    尺寸: {adjustingItem.targetWidth} x {adjustingItem.targetHeight}
                  </div>
                </div>
              )}
              
              {/* 调整手柄美化版 */}
              <div
                className="absolute right-0 bottom-0 cursor-nwse-resize select-none"
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
                    
                    // 更新调整状态
                    setAdjustingItem({
                      itemId: item.id,
                      targetWidth: newWidth,
                      targetHeight: newHeight
                    });
                  };
                  
                  const handleMouseUp = (upEvent: MouseEvent) => {
                    document.removeEventListener('mousemove', handleMouseMove);
                    document.removeEventListener('mouseup', handleMouseUp);
                    
                    // 如果adjustingItem存在，使用其中的目标尺寸
                    // 否则根据鼠标最终位置计算新尺寸
                    let finalWidth, finalHeight;
                    
                    if (adjustingItem) {
                      finalWidth = adjustingItem.targetWidth;
                      finalHeight = adjustingItem.targetHeight;
                    } else {
                      const deltaX = upEvent.clientX - startX;
                      const deltaY = upEvent.clientY - startY;
                      
                      // 根据单元格尺寸动态计算增量
                      const deltaColumns = Math.round(deltaX / cellWidth);
                      const deltaRows = Math.round(deltaY / cellHeight);
                      
                      finalWidth = Math.max(1, originalWidth + deltaColumns);
                      finalHeight = Math.max(1, originalHeight + deltaRows);
                    }
                    
                    // 检查新尺寸是否超出边界
                    if (item.x + finalWidth > layout.columns) {
                      finalWidth = layout.columns - item.x;
                      toast.warning("宽度已调整到边界");
                    }
                    
                    if (item.y + finalHeight > layout.rows) {
                      finalHeight = layout.rows - item.y;
                      toast.warning("高度已调整到边界");
                    }
                    
                    // 检查是否有重叠，使用合并的逻辑
                    const isOverlapping = checkOverlap(item.id, item.x, item.y, finalWidth, finalHeight);
                    
                    if (isOverlapping) {
                      toast.error("调整尺寸会与其他图表重叠");
                    } else {
                      // 同时更新宽度和高度
                      setLayout({
                        ...layout,
                        items: layout.items.map(i => 
                          i.id === item.id 
                            ? { ...i, width: finalWidth, height: finalHeight } 
                            : i
                        )
                      });
                      
                      toast.success(`已将图表尺寸调整为 ${finalWidth} x ${finalHeight}`);
                    }
                    
                    setAdjustingItem(null);
                  };
                  
                  document.addEventListener('mousemove', handleMouseMove);
                  document.addEventListener('mouseup', handleMouseUp);
                }}
              >
                {/* 美化后的调整手柄UI */}
                <div className="relative w-6 h-6 flex items-center justify-center">
                  <div className="absolute right-0.5 bottom-0.5 w-2 h-2 bg-gray-500 rounded-sm"></div>
                  <div className="absolute right-2.5 bottom-0.5 w-1.5 h-1 bg-gray-400 rounded-sm"></div>
                  <div className="absolute right-0.5 bottom-2.5 w-1 h-1.5 bg-gray-400 rounded-sm"></div>
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

  // 用于预览项目的新尺寸
  const renderPreviewOverlay = () => {
    if (!adjustingItem) return null;
    
    const item = layout.items.find(item => item.id === adjustingItem.itemId);
    if (!item) return null;
    
    return (
      <div
        className="absolute bg-blue-200 bg-opacity-30 border-2 border-blue-500 rounded-lg"
        style={{
          gridColumnStart: item.x + 1,
          gridColumnEnd: item.x + adjustingItem.targetWidth + 1,
          gridRowStart: item.y + 1,
          gridRowEnd: item.y + adjustingItem.targetHeight + 1,
          zIndex: 5,
          pointerEvents: 'none'
        }}
      >
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 bg-white px-2 py-1 rounded shadow text-sm">
          {adjustingItem.targetWidth} x {adjustingItem.targetHeight}
        </div>
      </div>
    );
  };
  
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>编辑布局</DialogTitle>
        </DialogHeader>
        
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">            
            {/* 布局 */}
            <div className="border rounded-lg p-4">
              <div 
                className="grid gap-1"
                style={{
                  gridTemplateColumns: `repeat(${layout.columns}, 1fr)`,
                  gridTemplateRows: `repeat(${layout.rows}, 150px)`,
                  position: 'relative'
                }}
              >
                {renderGrid()}
                {renderPreviewOverlay()}
              </div>
            </div>
            
            {/* 行列调整和导入导出 */}
            <div className="flex justify-between flex-wrap gap-4">
              <div className='flex-1'></div>
              <div className="flex items-center space-x-8">
                <div className="flex items-center space-x-4">
                  <Label htmlFor="columns">列数:</Label>
                  <div className="flex items-center space-x-1">
                    <div className="text-xl font-medium">{layout.columns}</div>
                    <div className="relative flex flex-col items-center">
                      <div className="flex flex-col -mt-1 space-y-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-4 w-4 rounded-b-none py-0"
                          onClick={() => adjustColumns(layout.columns + 1)}
                        >
                          <ChevronsUp className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-4 w-4 rounded-t-none py-0"
                          onClick={() => adjustColumns(layout.columns - 1)}
                          disabled={layout.columns <= 1}
                        >
                          <ChevronsDown className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="flex items-center space-x-4">
                  <Label htmlFor="rows">行数:</Label>
                  <div className="flex items-center space-x-1">
                  <div className="text-xl font-medium">{layout.rows}</div>
                  <div className="relative flex flex-col items-center">
                    <div className="flex flex-col -mt-1 space-y-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-4 w-4 rounded-b-none py-0"
                        onClick={() => adjustRows(layout.rows + 1)}
                      >
                        <ChevronsUp className="h-3 w-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-4 w-4 rounded-t-none py-0"
                        onClick={() => adjustRows(layout.rows - 1)}
                        disabled={layout.rows <= 1}
                      >
                        <ChevronsDown className="h-3 w-3" />
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
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
} 