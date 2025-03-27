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

  // 添加状态来跟踪调整中的单元格
  const [adjustingCell, setAdjustingCell] = useState<{rowId: string, cellId: string, targetWidth: number} | null>(null);

  // 调整总列数
  const adjustColumns = (newColumns: number) => {
    // 不允许列数小于1
    if (newColumns < 1) return;
    
    // 如果是减少列数
    if (newColumns < layout.columns) {
      // 检查是否存在某一行的所有单元格宽度都为1且占满整行
      const hasFullRowWithMinWidths = layout.rows.some(row => {
        const totalWidth = row.cells.reduce((sum, cell) => sum + cell.width, 0);
        const allCellsAreMinWidth = row.cells.every(cell => cell.width === 1);
        return totalWidth === layout.columns && allCellsAreMinWidth;
      });
      
      // 如果有这样的行，提示不能缩减列数
      if (hasFullRowWithMinWidths) {
        toast.error("存在行的所有单元格已是最小宽度且占满整行，无法减少列数");
        return;
      }
      
      // 处理每一行
      const updatedRows = layout.rows.map(row => {
        const totalWidth = row.cells.reduce((sum, cell) => sum + cell.width, 0);
        
        // 如果当前行已经不超过新列数，无需调整
        if (totalWidth <= newColumns) {
          return row;
        }
        
        // 需要减少的宽度
        let widthToReduce = totalWidth - newColumns;
        const cells = [...row.cells];
        
        // 先处理空隙
        if (totalWidth < layout.columns) {
          // 行有空隙，不需要调整单元格，直接返回
          return row;
        }
        
        // 找到第一个宽度大于1的单元格
        while (widthToReduce > 0) {
          // 找到第一个宽度大于1的单元格的索引
          const widerCellIndex = cells.findIndex(cell => cell.width > 1);
          
          if (widerCellIndex !== -1) {
            // 找到了宽度大于1的单元格，减少宽度
            cells[widerCellIndex] = {
              ...cells[widerCellIndex],
              width: cells[widerCellIndex].width - 1
            };
            widthToReduce--;
          } else {
            // 找不到宽度大于1的单元格，这种情况应该不会发生（因为前面已经检查过）
            // 但为了安全，我们提前退出循环
            break;
          }
        }
        
        return { ...row, cells };
      });
      
      setLayout({
        columns: newColumns,
        rows: updatedRows
      });
    } else {
      // 增加列数，简单更新
      setLayout({
        ...layout,
        columns: newColumns
      });
    }
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
        // 只移除单元格，不调整其他单元格宽度
        const updatedCells = r.cells.filter(cell => cell.id !== cellId);
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

  // 重新实现调整宽度的函数，控制灵敏度
  const handleResizeStart = (e: React.MouseEvent, rowId: string, cellId: string) => {
    e.preventDefault();
    
    // 记录起始位置和原始宽度
    const startX = e.clientX;
    
    // 找到当前单元格的宽度
    const rowIndex = layout.rows.findIndex(r => r.id === rowId);
    const cellIndex = layout.rows[rowIndex].cells.findIndex(c => c.id === cellId);
    const originalWidth = layout.rows[rowIndex].cells[cellIndex].width;
    
    console.log('开始调整宽度', rowId, cellId, '原始宽度:', originalWidth);
    
    // 设置较低的灵敏度
    const pixelsPerColumn = 150;
    let lastWidth = originalWidth;
    
    const handleMouseMove = (moveEvent: MouseEvent) => {
      // 计算水平方向移动的总距离
      const deltaX = moveEvent.clientX - startX;
      
      // 计算列数变化，使用更高的阈值
      const deltaColumns = Math.round(deltaX / pixelsPerColumn);
      
      // 计算新宽度
      let newWidth = originalWidth + deltaColumns;
      
      // 限制最小宽度为1
      newWidth = Math.max(1, newWidth);
      
      // 计算当前行其他单元格的总宽度
      const otherCellsWidth = layout.rows[rowIndex].cells.reduce((sum, cell, idx) => 
        idx === cellIndex ? sum : sum + cell.width, 0
      );
      
      // 确保不超过总列数
      newWidth = Math.min(newWidth, layout.columns - otherCellsWidth);
      
      // 更新辅助显示
      setAdjustingCell({rowId, cellId, targetWidth: newWidth});
      
      // 只有当宽度真的变化时才更新布局
      if (newWidth !== lastWidth) {
        lastWidth = newWidth;
        
        console.log('调整宽度到:', newWidth);
        
        // 更新布局
        setLayout(prevLayout => {
          const updatedRows = [...prevLayout.rows];
          
          updatedRows[rowIndex] = {
            ...updatedRows[rowIndex],
            cells: updatedRows[rowIndex].cells.map((cell, idx) => {
              if (idx === cellIndex) {
                return { ...cell, width: newWidth };
              }
              return cell;
            })
          };
          
          return {
            ...prevLayout,
            rows: updatedRows
          };
        });
      }
    };
    
    const handleMouseUp = () => {
      console.log('结束调整宽度');
      setAdjustingCell(null);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
    
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  // 处理保存
  const handleSave = () => {
    onSave(layout);
    onClose();
  };

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
                          
                          {/* 显示宽度信息 */}
                          <div className="absolute bottom-2 right-2 text-xs bg-white px-1 rounded opacity-70">
                            宽度: {cell.width}
                          </div>
                          
                          <div className="absolute top-2 left-2 flex">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-red-500"
                              onClick={() => removeCell(row.id, cell.id)}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                          
                          {/* 如果是正在调整的单元格，显示目标宽度 */}
                          {adjustingCell && adjustingCell.cellId === cell.id && adjustingCell.rowId === row.id && (
                            <div className="absolute inset-0 bg-blue-200 bg-opacity-50 flex items-center justify-center">
                              <div className="bg-white p-2 rounded shadow">
                                目标宽度: {adjustingCell.targetWidth}
                              </div>
                            </div>
                          )}
                          
                          {/* 更改拖动手柄 */}
                          <div
                            className="absolute right-0 top-0 bottom-0 w-6 bg-blue-500 opacity-50 hover:opacity-80 cursor-col-resize"
                            onMouseDown={(e) => handleResizeStart(e, row.id, cell.id)}
                            style={{
                              zIndex: 10
                            }}
                          ></div>
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