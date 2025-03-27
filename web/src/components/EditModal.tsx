import  { useEffect, useState } from 'react';
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Filter, Database, BarChart2, Pencil, Trash2, Plus } from 'lucide-react';
import { toast } from "sonner"
import { DataSourceModal } from "./DataSourceModal";
import {EditLayoutModal} from './EditLayoutModal';

import  type {DataSource, Layout, Parameter, Chart, Report} from '@/types';
import { addItem as addLayoutItem, removeEmptyRowsAndColumns } from '@/types/models/layout';

interface EditModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (params: any[], visualizations: any[], sqlCode: string) => void;
  reportId: string;
}

const EditModal = ({ 
  open, 
  onClose,
  reportId
}: EditModalProps) => {

  // todo: 获取报表的布局
  console.log('reportId', reportId);
  // 构造 demo 数据
  const demoReport = {
    title: "销售报表",
    description: "这是一个销售数据的示例报表",
    dataSources: [
      { id: 'ds1', type: 'MYSQL', alias: '销售数据' },
      { id: 'ds2', type: 'API', alias: '外部数据' }
    ],
    parameters: [
      { id: 'param1', name: '开始日期', type: 'date' },
      { id: 'param2', name: '结束日期', type: 'date' }
    ],
    charts: [
      { id: 'item-1', title: '销售趋势', code: 'line', dependencies: ['ds1'], executor: { type: 'python', engine: 'pandas' } },
      { id: 'item-2', title: '销售占比', code: 'pie', dependencies: ['ds2'], executor: { type: 'python', engine: 'pandas' } },
      { id: 'item-3', title: '销售占比', code: 'pie', dependencies: ['ds2'], executor: { type: 'python', engine: 'pandas' } },
      { id: 'item-4', title: '销售占比', code: 'pie', dependencies: ['ds2'], executor: { type: 'python', engine: 'pandas' } },
      { id: 'item-5', title: '销售占比', code: 'pie', dependencies: ['ds2'], executor: { type: 'python', engine: 'pandas' } },
      { id: 'item-6', title: '销售占比', code: 'pie', dependencies: ['ds2'], executor: { type: 'python', engine: 'pandas' } }
    ],
    layout: {
      columns: 3,
      rows: 2,
      items: [
        { id: 'item-1', title: '销售趋势', width: 1, height: 1, x: 0, y: 0 },
        { id: 'item-2', title: '销售占比', width: 1, height: 1, x: 1, y: 0 },
        { id: 'item-3', title: '销售明细', width: 1, height: 1, x: 2, y: 0 },
        { id: 'item-4', title: '新增图表1', width: 1, height: 1, x: 0, y: 1 },
        { id: 'item-5', title: '新增图表2', width: 1, height: 1, x: 1, y: 1 },
        { id: 'item-6', title: '新增图表333', width: 1, height: 1, x: 2, y: 1 }
      ]
    }};
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [parameters, setParameters] = useState<Parameter[]>([]);
  const [charts, setCharts] = useState<Chart[]>(demoReport.charts);
  const [layout, setLayout] = useState<Layout>(demoReport.layout);

  const [activeTab, setActiveTab] = useState('filters');
  const [isDataSourceModalOpen, setIsDataSourceModalOpen] = useState(false)
  const [isLayoutModalOpen, setIsLayoutModalOpen] = useState(false);

  const handleSaveLayout = (layout: any) => {
    setLayout(layout);
    setIsLayoutModalOpen(false);
  };

  // 添加图表
  const handleAddChart = () => {
    // 提取现有图表的 ID，并转换为数字
    const existingIds = charts.map(chart => parseInt(chart.id.split('-')[1], 10));

    // 找到缺失的最小数字
    let newId = 1;
    while (existingIds.includes(newId)) {
      newId++;
    }

    // 生成新的 ID
    const newChartId = `item-${newId}`;
    const title = `新增图表 ${newId}`;

    // 添加新的图表
    setCharts([...charts, { 
      id: newChartId, 
      title: title, 
      code: 'pie', 
      dependencies: [], 
      executor: { type: 'python', engine: 'pandas' } 
    }]);

    // 更新布局
    setLayout(addLayoutItem(layout, newChartId, title));
  };

  // 删除图表
  const handleDeleteChart = (chartId: string) => {
    if (charts.length === 1) {
      toast.error('至少需要保留一个图表');
      return;
    }
    // 删除图表
    setCharts(charts.filter(chart => chart.id !== chartId));
    
    // 更新布局，删除对应的 item
    let newLayout = {
      ...layout,
      items: layout.items.filter(item => item.id !== chartId) // 过滤掉被删除的 item
    }
    // 删除空行和空列
    newLayout = removeEmptyRowsAndColumns(newLayout)
    setLayout(newLayout);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onClose}>
        <DialogContent className="max-w-[90vw] h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>编辑报表</DialogTitle>
          </DialogHeader>
          
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden">
            <TabsList className="w-full grid grid-cols-3 sticky top-0 z-10">
              <TabsTrigger value="data" className="flex items-center gap-2">
                <Database size={24} />
                <span>数据源</span>
              </TabsTrigger>

              <TabsTrigger value="filters" className="flex items-center gap-2">
                <Filter size={24} />
                <span>筛选条件</span>
              </TabsTrigger>

              <TabsTrigger value="charts" className="flex items-center gap-2">
                <BarChart2 size={24} />
                <span>图表</span>
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 overflow-y-auto">
              {/* 数据标签页 */}
              <TabsContent value="data" className="p-4">
                <div className="space-y-4">
                  <div className="space-y-3">
                    <div className="border rounded-lg p-4 bg-white shadow-sm">
                      {/* 显示当前数据源配置的摘要信息 */}
                      <div className="flex justify-between items-center">
                        <div>
                          <h4 className="font-medium">数据源1</h4>
                          <p className="text-sm text-gray-500">type: MYSQL</p>
                          <p className="text-sm text-gray-500">alias: df, df1</p>
                        </div>
                        <div className="flex gap-2">
                                <Button variant="ghost" size="icon" className="h-8 w-8">
                                  <Pencil className="h-4 w-4" />
                                </Button>
                                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                        </div>
                      </div>
                    </div>

                    <div className="border rounded-lg p-4 bg-white shadow-sm">
                      {/* 显示当前数据源配置的摘要信息 */}
                      <div className="flex justify-between items-center">
                        <div>
                          <h4 className="font-medium">数据源2</h4>
                          <p className="text-sm text-gray-500">python</p>
                          <p className="text-sm text-gray-500">dataframe: df2</p>
                        </div>
                        <div className="flex gap-2">
                                <Button variant="ghost" size="icon" className="h-8 w-8">
                                  <Pencil className="h-4 w-4" />
                                </Button>
                                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 添加数据源 */}
                  <div className="mt-6">
                    <Button 
                      variant="outline" 
                      className="w-full border-dashed"
                      onClick={() => {setIsDataSourceModalOpen(true)}}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      添加数据源
                    </Button>
                  </div>
                </div>
              </TabsContent>

              {/* 筛选条件标签页 */}
              <TabsContent value="filters" className="p-4">
                <div className="space-y-4">
                  
                  <div className="space-y-3">
                    {/* 时间范围卡片 */}
                    <div className="border rounded-lg p-4 bg-white shadow-sm">
                      <div className="flex justify-between items-center">
                        <div>
                          <h4 className="font-medium">时间范围</h4>
                          <p className="text-sm text-gray-500">日期选择器</p>
                        </div>
                        <div className="flex gap-2">
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>

                    {/* 区域卡片 */}
                    <div className="border rounded-lg p-4 bg-white shadow-sm">
                      <div className="flex justify-between items-center">
                        <div>
                          <h4 className="font-medium">区域</h4>
                          <p className="text-sm text-gray-500">下拉选择器</p>
                        </div>
                        <div className="flex gap-2">
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>

                    {/* 产品类别卡片 */}
                    <div className="border rounded-lg p-4 bg-white shadow-sm">
                      <div className="flex justify-between items-center">
                        <div>
                          <h4 className="font-medium">产品类别</h4>
                          <p className="text-sm text-gray-500">下拉选择器</p>
                        </div>
                        <div className="flex gap-2">
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive">
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 添加筛选条件按钮 */}
                  <div className="mt-6">
                    <Button 
                      variant="outline" 
                      className="w-full border-dashed"
                      onClick={() => {}}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      添加筛选条件
                    </Button>
                  </div>
                </div>
              </TabsContent>

              {/* 图表管理标签页 */}
              <TabsContent value="charts" className="p-4">
                <div className="space-y-4">
                  <div className="border rounded-lg p-4">
                    {/* 布局预览区域 - 使用动态布局 */}
                    {layout ? (
                      <div 
                        className="grid gap-4 relative" 
                        style={{ 
                          gridTemplateColumns: `repeat(${layout.columns}, 1fr)`,
                          gridTemplateRows: `repeat(${layout.rows}, 100px)`, // 使用固定行高
                          minHeight: '100px' // 确保有足够的高度
                        }}
                      >
                        {/* 先渲染所有项目 */}
                        {layout.items.map((item) => (
                          <div 
                            key={item.id}
                            className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200 flex items-center justify-center relative group"
                            style={{
                              gridColumn: `${item.x + 1} / span ${item.width}`,
                              gridRow: `${item.y + 1} / span ${item.height}`
                            }}
                          >
                            {item.title}

                            {/* 在右上角添加图标，默认隐藏 */}
                            <div className="absolute top-0 right-0 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-6 w-6" 
                                onClick={() => {/* 编辑逻辑 */}}
                              >
                                <Pencil className="h-4 w-4" />
                              </Button>
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                className="h-6 w-6 text-destructive" 
                                onClick={() => {
                                  const confirmed = window.confirm("您确定要删除这个图表吗？");
                                  if (confirmed) {
                                    handleDeleteChart(item.id); // 调用删除逻辑
                                  }
                                }}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        ))}
                          
                        {/* 然后渲染空白单元格（不被项目占据的部分） */}
                        {Array.from({ length: layout.rows }).map((_, rowIndex) => (
                          Array.from({ length: layout.columns }).map((_, colIndex) => {
                            // 检查这个单元格是否被任何项目占据
                            const isCellOccupied = layout.items.some(item => 
                              colIndex >= item.x && 
                              colIndex < item.x + item.width && 
                              rowIndex >= item.y && 
                              rowIndex < item.y + item.height
                            );
                            
                            // 如果单元格未被占据，则渲染空白格
                            return !isCellOccupied ? (
                              <div 
                                key={`empty-${rowIndex}-${colIndex}`} 
                                className="border-2 border-dashed rounded-lg p-4 text-center flex items-center justify-center"
                                style={{
                                  gridColumn: `${colIndex + 1}`,
                                  gridRow: `${rowIndex + 1}`
                                }}
                              >
                                {/* 空白格可以显示提示信息或保持空白 */}
                              </div>
                            ) : null;
                          })
                        ))}
                      </div>
                    ) : (
                      <div className="text-center p-4">正在加载布局...</div>
                    )}
                  </div>

                  <div className="mt-6">
                    <Button 
                      variant="outline" 
                      className="w-full border-dashed"
                      onClick={() => {handleAddChart()}}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      添加图表
                    </Button>
                    <Button 
                      variant="outline" 
                      className="w-full border-dashed mt-2"
                      onClick={() => setIsLayoutModalOpen(true)}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      修改布局
                    </Button>
                  </div>
                </div>
              </TabsContent>
            </div>
          </Tabs>
        </DialogContent>
      </Dialog>

      <DataSourceModal
        open={isDataSourceModalOpen}
        onClose={() => setIsDataSourceModalOpen(false)}
        onSave = {() => {}}
      />

      <EditLayoutModal
        open={isLayoutModalOpen}
        onClose={() => setIsLayoutModalOpen(false)}
        onSave={handleSaveLayout}
        initialLayout={layout}
      />
    </>
  );
};

export default EditModal; 