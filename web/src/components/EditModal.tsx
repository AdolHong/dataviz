import { useState } from 'react';
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Filter, Database, BarChart2, Pencil, Trash2, Plus } from 'lucide-react';
import axios from 'axios';
import { toast } from "sonner"
import { DataSourceModal } from "./DataSourceModal";
import {EditLayoutModal} from './EditLayoutModal';

interface EditModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (params: any[], visualizations: any[], sqlCode: string) => void;
  parameters: any[];
  visualizations?: any[];
  dashboardConfig: any;
  initialSqlCode: string;
}

const EditModal = ({ 
  open, 
  onClose
}: EditModalProps) => {
  const [activeTab, setActiveTab] = useState('filters');
  const [isDataSourceModalOpen, setIsDataSourceModalOpen] = useState(false)
  const [isLayoutModalOpen, setIsLayoutModalOpen] = useState(false);

  const handleSaveLayout = (layout: any) => {
    toast('保存的布局:', layout);
    setIsLayoutModalOpen(false);
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
                    {/* 布局预览区域 */}
                    <div className="grid grid-cols-3 gap-4">
                      <div className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200">
                        销售趋势
                      </div>
                      <div className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200">
                        销售占比
                      </div>
                      <div className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200">
                        销售明细
                      </div>
                      <div className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200 col-span-2">
                        新增图表1
                      </div>
                      <div className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200">
                        新增图表2
                      </div>
                      <div className="border-2 border-dashed rounded-lg p-4 text-center bg-gray-200 col-span-3">
                        新增图表3
                      </div>
                    </div>
                  </div>

                  <div className="mt-6">
                    <Button 
                      variant="outline" 
                      className="w-full border-dashed"
                      onClick={() => {}}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      添加图表
                    </Button>
                    <Button 
                      variant="outline" 
                      className="w-full border-dashed"
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
        initialLayout={{
          columns: 3,
          rows: 2,
          items: [
            { id: 'item-1', title: '销售趋势', width: 1, height: 1, x: 0, y: 0 },
            { id: 'item-2', title: '销售占比', width: 1, height: 1, x: 1, y: 0 },
            { id: 'item-3', title: '销售明细', width: 1, height: 1, x: 2, y: 0 },
            { id: 'item-4', title: '新增图表1', width: 1, height: 1, x: 0, y: 1 },
            { id: 'item-5', title: '新增图表2', width: 1, height: 1, x: 1, y: 1 },
            { id: 'item-6', title: '新增图表3', width: 1, height: 1, x: 2, y: 1 }
          ]
        }}
      />
    </>
  );
};

export default EditModal; 