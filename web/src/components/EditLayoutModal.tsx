import { useState, useEffect } from 'react';
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Grip, Plus, Trash2, ArrowLeft, ArrowRight } from 'lucide-react';
import { toast } from "sonner";

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
    rows: [
      {
        id: 'row-1',
        cells: [
          { id: 'cell-1', title: '销售趋势', width: 1 },
          { id: 'cell-2', title: '区域销售占比', width: 1 },
          { id: 'cell-3', title: '销售明细数据', width: 1 },
        ]
      },
      {
        id: 'row-2',
        cells: [
          { id: 'cell-4', title: '新增图表1', width: 2 },
          { id: 'cell-5', title: '新增图表2', width: 1 },
        ]
      },
      {
        id: 'row-3',
        cells: [
          { id: 'cell-6', title: '新增图表3', width: 3 },
        ]
      }
    ]
  };

  // 初始化布局状态
  const [layout, setLayout] = useState<Layout>(initialLayout || defaultLayout);
  const [draggingItem, setDraggingItem] = useState<string | null>(null);
  const [resizingItem, setResizingItem] = useState<string | null>(null);
  const [startResizeX, setStartResizeX] = useState<number>(0);
  const [originalWidth, setOriginalWidth] = useState<number>(0);

  // 调整总列数
  const adjustColumns = (newColumns: number) => {
    if (newColumns < 1) return;
    
    // 确保所有行的单元格宽度总和不超过新的列数
    const updatedRows = layout.rows.map(row => {
      const totalWidth = row.cells.reduce((sum, cell) => sum + cell.width, 0);
      
      if (totalWidth > newColumns) {
        // 需要调整单元格宽度
        const cells = [...row.cells];
        let excess = totalWidth - newColumns;
        
        // 从最宽的单元格开始缩小
        while (excess > 0) {
          const widestCellIndex = cells.findIndex(cell => 
            cell.width === Math.max(...cells.map(c => c.width))
          );
          
          if (cells[widestCellIndex].width > 1) {
            cells[widestCellIndex] = {
              ...cells[widestCellIndex],
              width: cells[widestCellIndex].width - 1
            };
            excess--;
          } else {
            // 如果所有单元格都是最小宽度，则移除最后一个单元格
            if (cells.length > 1) {
              cells.pop();
              excess--;
            } else {
              break;
            }
          }
        }
        
        return { ...row, cells };
      }
      
      return row;
    });
    
    setLayout({
      columns: newColumns,
      rows: updatedRows
    });
  };

  // 添加新行
  const addRow = () => {
    const newRowId = `row-${Date.now()}`;
    const newCellId = `cell-${Date.now()}`;
    
    setLayout({
      ...layout,
      rows: [
        ...layout.rows,
        {
          id: newRowId,
          cells: [
            { id: newCellId, title: '新图表', width: layout.columns }
          ]
        }
      ]
    });
  };

  // 删除行
  const removeRow = (rowId: string) => {
    if (layout.rows.length <= 1) {
      toast.error("至少保留一行");
      return;
    }
    
    setLayout({
      ...layout,
      rows: layout.rows.filter(row => row.id !== rowId)
    });
  };

  // 添加单元格
  const addCell = (rowId: string) => {
    const row = layout.rows.find(r => r.id === rowId);
    if (!row) return;
    
    const currentTotalWidth = row.cells.reduce((sum, cell) => sum + cell.width, 0);
    if (currentTotalWidth >= layout.columns) {
      toast.error("此行已满，无法添加更多单元格");
      return;
    }
    
    const availableWidth = layout.columns - currentTotalWidth;
    const updatedRows = layout.rows.map(r => {
      if (r.id === rowId) {
        return {
          ...r,
          cells: [
            ...r.cells,
            { id: `cell-${Date.now()}`, title: '新图表', width: availableWidth }
          ]
        };
      }
      return r;
    });
    
    setLayout({ ...layout, rows: updatedRows });
  };

  // 删除单元格
  const removeCell = (rowId: string, cellId: string) => {
    const row = layout.rows.find(r => r.id === rowId);
    if (!row || row.cells.length <= 1) {
      toast.error("每行至少需要一个单元格");
      return;
    }
    
    const updatedRows = layout.rows.map(r => {
      if (r.id === rowId) {
        // 移除单元格
        const updatedCells = r.cells.filter(cell => cell.id !== cellId);
        
        // 将剩余空间分配给最后一个单元格
        const currentTotalWidth = updatedCells.reduce((sum, cell) => sum + cell.width, 0);
        const remainingWidth = layout.columns - currentTotalWidth;
        
        if (remainingWidth > 0 && updatedCells.length > 0) {
          const lastCell = updatedCells[updatedCells.length - 1];
          updatedCells[updatedCells.length - 1] = {
            ...lastCell,
            width: lastCell.width + remainingWidth
          };
        }
        
        return { ...r, cells: updatedCells };
      }
      return r;
    });
    
    setLayout({ ...layout, rows: updatedRows });
  };

  // 修改单元格标题
  const updateCellTitle = (rowId: string, cellId: string, title: string) => {
    const updatedRows = layout.rows.map(row => {
      if (row.id === rowId) {
        const updatedCells = row.cells.map(cell => {
          if (cell.id === cellId) {
            return { ...cell, title };
          }
          return cell;
        });
        return { ...row, cells: updatedCells };
      }
      return row;
    });
    
    setLayout({ ...layout, rows: updatedRows });
  };

  // 调整单元格宽度
  const handleResizeStart = (e: React.MouseEvent, rowId: string, cellId: string) => {
    e.preventDefault();
    setResizingItem(`${rowId}-${cellId}`);
    setStartResizeX(e.clientX);
    
    // 找到单元格当前宽度
    const row = layout.rows.find(r => r.id === rowId);
    const cell = row?.cells.find(c => c.id === cellId);
    if (cell) {
      setOriginalWidth(cell.width);
    }
    
    // 添加全局鼠标事件监听器
    document.addEventListener('mousemove', handleResizeMove);
    document.addEventListener('mouseup', handleResizeEnd);
  };

  const handleResizeMove = (e: MouseEvent) => {
    if (!resizingItem) return;
    
    const [rowId, cellId] = resizingItem.split('-');
    const deltaX = e.clientX - startResizeX;
    
    // 将像素位移转换为列数变化
    // 假设每列宽度为100px
    const columnWidth = 100;
    const deltaColumns = Math.round(deltaX / columnWidth);
    
    if (deltaColumns === 0) return;
    
    // 找到行和单元格
    const rowIndex = layout.rows.findIndex(r => r.id === rowId);
    if (rowIndex === -1) return;
    
    const cellIndex = layout.rows[rowIndex].cells.findIndex(c => c.id === cellId);
    if (cellIndex === -1) return;
    
    // 计算新宽度
    let newWidth = originalWidth + deltaColumns;
    
    // 确保宽度至少为1
    newWidth = Math.max(1, newWidth);
    
    // 计算行中所有单元格的总宽度
    const totalWidthWithoutCurrentCell = layout.rows[rowIndex].cells.reduce((sum, cell, idx) => {
      return idx === cellIndex ? sum : sum + cell.width;
    }, 0);
    
    // 确保不超过总列数
    newWidth = Math.min(newWidth, layout.columns - totalWidthWithoutCurrentCell);
    
    // 更新布局
    const updatedRows = [...layout.rows];
    updatedRows[rowIndex] = {
      ...updatedRows[rowIndex],
      cells: updatedRows[rowIndex].cells.map((cell, idx) => {
        if (idx === cellIndex) {
          return { ...cell, width: newWidth };
        }
        return cell;
      })
    };
    
    setLayout({ ...layout, rows: updatedRows });
    setStartResizeX(e.clientX);
    setOriginalWidth(newWidth);
  };

  const handleResizeEnd = () => {
    setResizingItem(null);
    document.removeEventListener('mousemove', handleResizeMove);
    document.removeEventListener('mouseup', handleResizeEnd);
  };

  // 处理保存
  const handleSave = () => {
    onSave(layout);
    onClose();
  };

  // 清理事件监听器
  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleResizeMove);
      document.removeEventListener('mouseup', handleResizeEnd);
    };
  }, []);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>编辑布局</DialogTitle>
        </DialogHeader>
        
        <div className="flex-1 overflow-y-auto p-4">
          <div className="space-y-4">
            {/* 全局设置 */}
            <div className="flex items-center space-x-4">
              <Label htmlFor="columns">总列数:</Label>
              <div className="flex items-center">
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => adjustColumns(layout.columns - 1)}
                  disabled={layout.columns <= 1}
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <span className="w-8 text-center">{layout.columns}</span>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => adjustColumns(layout.columns + 1)}
                >
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
              <Button onClick={addRow} variant="outline" className="ml-auto">
                <Plus className="h-4 w-4 mr-2" />
                添加行
              </Button>
            </div>
            
            {/* 布局预览 */}
            <div className="border rounded-lg p-4">
              <h3 className="font-medium mb-4">布局预览</h3>
              
              <div className="space-y-8">
                {layout.rows.map((row) => (
                  <div key={row.id} className="relative border-t border-dashed pt-4">
                    <div className="absolute -top-3 left-0 bg-white px-2 text-xs text-gray-500 flex items-center">
                      <Grip className="h-3 w-3 mr-1" />
                      行 {layout.rows.indexOf(row) + 1}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 ml-2 text-red-500"
                        onClick={() => removeRow(row.id)}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 text-blue-500"
                        onClick={() => addCell(row.id)}
                      >
                        <Plus className="h-3 w-3" />
                      </Button>
                    </div>
                    
                    <div
                      className="grid gap-4"
                      style={{
                        gridTemplateColumns: `repeat(${layout.columns}, 1fr)`,
                      }}
                    >
                      {row.cells.map((cell) => (
                        <div
                          key={cell.id}
                          className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200 relative"
                          style={{
                            gridColumn: `span ${cell.width} / span ${cell.width}`,
                          }}
                        >
                          <input
                            type="text"
                            value={cell.title}
                            onChange={(e) => updateCellTitle(row.id, cell.id, e.target.value)}
                            className="bg-transparent text-center w-full border-none"
                          />
                          <div className="absolute top-2 right-2 flex">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-red-500"
                              onClick={() => removeCell(row.id, cell.id)}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                          
                          {/* 调整宽度的拖动手柄 */}
                          <div
                            className="absolute right-0 top-0 bottom-0 w-2 cursor-col-resize bg-blue-400 bg-opacity-0 hover:bg-opacity-25"
                            onMouseDown={(e) => handleResizeStart(e, row.id, cell.id)}
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            {/* 导入/导出 */}
            <div className="flex justify-between">
              <Button
                variant="outline"
                onClick={() => {
                  try {
                    const jsonStr = JSON.stringify(layout, null, 2);
                    navigator.clipboard.writeText(jsonStr);
                    toast.success("布局已复制到剪贴板");
                  } catch (error) {
                    toast.error("导出失败");
                  }
                }}
              >
                导出布局
              </Button>
              
              <Button
                variant="outline"
                onClick={() => {
                  try {
                    // 创建一个输入框让用户粘贴JSON
                    const jsonStr = prompt("请粘贴布局JSON:");
                    if (jsonStr) {
                      const newLayout = JSON.parse(jsonStr);
                      // 简单验证
                      if (
                        typeof newLayout.columns === 'number' && 
                        Array.isArray(newLayout.rows)
                      ) {
                        setLayout(newLayout);
                        toast.success("布局已导入");
                      } else {
                        toast.error("无效的布局格式");
                      }
                    }
                  } catch (error) {
                    toast.error("导入失败，请检查JSON格式");
                  }
                }}
              >
                导入布局
              </Button>
            </div>
          </div>
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={handleSave}>保存布局</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
} 