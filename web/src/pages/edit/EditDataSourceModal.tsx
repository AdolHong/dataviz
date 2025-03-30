import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  type DataSource,
  type PythonSourceExecutor,
  type SQLSourceExecutor,
  type CSVSourceExecutor,
  type CSVUploaderSourceExecutor,
  handleExecutorTypeChange,
  handleUpdateModeChange,
  handleEngineChange,
} from '@/types/models/dataSource';
import { CSVTable } from '@/components/CSVTable';
import type { EngineChoices, AliasRelianceMap } from '@/types';

import AceEditor from 'react-ace';
import 'ace-builds/src-noconflict/theme-xcode';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/mode-sql';
import { toast } from 'sonner';

interface EditDataSourceModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (dataSource: DataSource) => void;
  initialDataSource?: DataSource | null;
  engineChoices: EngineChoices;
  existingAliases: string[];
  aliasRelianceMap: AliasRelianceMap;
}

export const EditDataSourceModal = ({
  open,
  onClose,
  onSave,
  initialDataSource = null,
  engineChoices, // 引擎的选项
  existingAliases, // 已存在的别名
  aliasRelianceMap, // 依赖的图表
}: EditDataSourceModalProps) => {
  // 默认布局
  const defaultDataSource: DataSource = {
    id: '',
    name: '数据名称',
    description: '',
    alias: 'df_',
    executor: {
      type: 'sql',
      engine: 'default',
      code: 'select 1',
      updateMode: { type: 'manual' },
    },
  };
  // 没有open返回
  if (!open) return;

  const [dataSource, setDataSource] = useState<DataSource>(defaultDataSource);

  useEffect(() => {
    setDataSource(initialDataSource || defaultDataSource);
  }, [open]);

  const handleSave = () => {
    // 简单的验证
    if (!dataSource.name) {
      toast.error('请输入数据源名称');
      return;
    }

    // 根据执行器类型验证
    if (['python', 'sql'].includes(dataSource.executor?.type || '')) {
      if (
        !(dataSource.executor as PythonSourceExecutor | SQLSourceExecutor).code
      ) {
        toast.error('请输入代码');
        return;
      }
    } else if (dataSource.executor?.type === 'csv_data') {
      if (!(dataSource.executor as CSVSourceExecutor).data) {
        toast.error('请上传CSV数据');
        return;
      }
    } else if (dataSource.executor?.type === 'csv_uploader') {
      if (!(dataSource.executor as CSVUploaderSourceExecutor).demoData) {
        toast.error('请上传示例CSV数据');
        return;
      }
    }

    // 别名不能重复
    if (existingAliases.includes(dataSource.alias)) {
      toast.error('别名不能重复');
      return;
    }

    // 别名为前缀_df
    if (dataSource.alias === 'df_') {
      toast.error('请修改别名，别名不能为df_');
      return;
    }

    // 保存
    onSave(dataSource);
    onClose();
  };

  // 获取执行器类型
  const executorType = dataSource.executor?.type || 'sql';

  // 检查是否显示代码编辑器（仅 python 和 sql 需要）
  const showCodeEditor = ['python', 'sql'].includes(executorType);

  // 检查是否显示CSV上传器（仅 csv_data 和 csv_uploader 需要）
  const showCSVUploader = ['csv_data', 'csv_uploader'].includes(executorType);

  // 获取更新模式（仅 python 和 sql 有）
  const updateMode = showCodeEditor
    ? (dataSource.executor as PythonSourceExecutor | SQLSourceExecutor)
        .updateMode?.type || 'manual'
    : 'manual';

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className='max-w-3xl h-[80vh] max-h-[90vh] flex flex-col overflow-hidden'>
        <DialogHeader>
          <DialogTitle>
            {initialDataSource ? '编辑数据源' : '新建数据源'}
          </DialogTitle>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='flex items-center space-x-6'>
            <div className='flex items-center space-x-2'>
              <label className='whitespace-nowrap min-w-8 mr-4 flex items-center'>
                名称
              </label>
              <Input
                value={dataSource.name || ''}
                onChange={(e) =>
                  setDataSource((prev) => ({ ...prev, name: e.target.value }))
                }
                placeholder='输入数据源名称'
              />
            </div>
            <div className='flex items-center space-x-2'>
              <label className='whitespace-nowrap min-w-8 mr-4 flex items-center'>
                别名
              </label>
              <Input
                value={dataSource.alias || 'df_'}
                onChange={(e) => {
                  // 如果存在依赖不能修改
                  if (
                    aliasRelianceMap.aliasToArtifacts[dataSource.alias] &&
                    dataSource.id ===
                      aliasRelianceMap.aliasToDataSourceId[dataSource.alias]
                  ) {
                    toast.error('存在依赖不能修改');
                    return;
                  }

                  // 别名必须以df_开头
                  if (!e.target.value.startsWith('df_')) {
                    toast.error('别名必须以df_开头');
                    return;
                  }

                  // 修改别名
                  setDataSource((prev) => ({
                    ...prev,
                    alias: e.target.value,
                  }));
                }}
                placeholder='输入数据源别名'
              />
            </div>
          </div>

          <div className='flex items-center'>
            <label className='block mb-2 w-30 h-10 flex items-center'>
              描述（可选）
            </label>
            <Input
              value={dataSource.description || ''}
              onChange={(e) =>
                setDataSource((prev) => ({
                  ...prev,
                  description: e.target.value,
                }))
              }
              placeholder='输入数据源描述'
              className='h-10'
            />
          </div>

          <div className='flex space-x-10'>
            <div>
              <label className='block mb-2'>执行器类型</label>
              <Select
                value={executorType}
                onValueChange={(newExecutorType) =>
                  setDataSource(
                    handleExecutorTypeChange(
                      dataSource,
                      newExecutorType as
                        | 'python'
                        | 'sql'
                        | 'csv_data'
                        | 'csv_uploader'
                    )
                  )
                }
              >
                <SelectTrigger className='w-45'>
                  <SelectValue placeholder='选择执行器类型' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='python'>Python</SelectItem>
                  <SelectItem value='sql'>SQL</SelectItem>
                  <SelectItem value='csv_data'>CSV 固定数据集</SelectItem>
                  <SelectItem value='csv_uploader'>CSV 上传器</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='flex-1'></div>
            {showCodeEditor && (
              <div>
                <label className='block mb-2'>计算引擎</label>
                <Select
                  value={
                    (
                      dataSource.executor as
                        | PythonSourceExecutor
                        | SQLSourceExecutor
                    )?.engine ||
                    engineChoices[executorType as keyof EngineChoices][0]
                  }
                  onValueChange={(engine) => {
                    setDataSource(handleEngineChange(dataSource, engine));
                  }}
                >
                  <SelectTrigger className='w-45'>
                    <SelectValue placeholder='选择引擎' />
                  </SelectTrigger>
                  <SelectContent>
                    {engineChoices[executorType as keyof EngineChoices].map(
                      (engine) => (
                        <SelectItem value={engine}>{engine}</SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>
            )}

            {showCSVUploader && (
              <div>
                <label className='block mb-2'>上传</label>
                <button
                  type='button'
                  className='py-1 h-8 w-45 shadow-sm  rounded-sm hover:bg-blue-100 transition-colors'
                  onClick={() => {
                    // 这里应当触发文件上传，为简化代码，仅模拟
                    const mockData =
                      'id,name,value1,value2,value3,value4,value5,value6,value7,value8,value9,value10,value11,value12,value13,value14,value15,value16,value17,value18,value19,value20\n1,测试1,10,20,30,40,50,60,70,80,90,100,110,120,130,140,150,160,170,180\n2,测试2,15,25,35,45,55,65,75,85,95,105,115,125,135,145,155,165,175,185\n3,测试3,20,30,40,50,60,70,80,90,100,110,120,130,140,150,160,170,180,190\n4,测试4,25,35,45,55,65,75,85,95,105,115,125,135,145,155,165,175,185,195\n5,测试5,30,40,50,60,70,80,90,100,110,120,130,140,150,160,170,180,190,200\n6,测试6,35,45,55,65,75,85,95,105,115,125,135,145,155,165,175,185,195,205\n7,测试7,40,50,60,70,80,90,100,110,120,130,140,150,160,170,180,190,200,210\n8,测试8,45,55,65,75,85,95,105,115,125,135,145,155,165,175,185,195,205,215\n9,测试9,50,60,70,80,90,100,110,120,130,140,150,160,170,180,190,200,210,220\n10,测试10,55,65,75,85,95,105,115,125,135,145,155,165,175,185,195,205,215,225';
                    if (executorType === 'csv_data') {
                      setDataSource((prev) => ({
                        ...prev,
                        executor: {
                          ...(prev.executor as CSVSourceExecutor),
                          data: mockData,
                        },
                      }));
                    } else {
                      setDataSource((prev) => ({
                        ...prev,
                        executor: {
                          ...(prev.executor as CSVUploaderSourceExecutor),
                          demoData: mockData,
                        },
                      }));
                    }
                  }}
                >
                  {executorType === 'csv_data'
                    ? ' CSV 数据'
                    : ' 示例 CSV 数据 '}
                </button>
              </div>
            )}
          </div>

          {showCodeEditor && (
            <>
              <div>
                <label className='block mb-2'>代码</label>
                <AceEditor
                  mode={executorType === 'python' ? 'python' : 'sql'}
                  theme='xcode'
                  name='codeEditor'
                  height='200px'
                  width='100%'
                  onChange={(value) => {
                    setDataSource((prev) => ({
                      ...prev,
                      executor: {
                        ...(prev.executor as
                          | PythonSourceExecutor
                          | SQLSourceExecutor),
                        code: value,
                      },
                    }));
                  }}
                  value={
                    executorType === 'python' || executorType === 'sql'
                      ? (
                          dataSource.executor as
                            | PythonSourceExecutor
                            | SQLSourceExecutor
                        ).code || ''
                      : ''
                  }
                />
              </div>
              <div className='flex space-x-10'>
                <div>
                  <label className='block mb-2'>更新模式</label>
                  <RadioGroup
                    value={updateMode}
                    onValueChange={(value) =>
                      setDataSource(
                        handleUpdateModeChange(
                          dataSource,
                          value as 'manual' | 'auto'
                        )
                      )
                    }
                    className='flex gap-4 h-10'
                  >
                    <div className='flex items-center space-x-2'>
                      <RadioGroupItem value='manual' id='manual' />
                      <Label htmlFor='manual'>手动更新</Label>
                    </div>
                    <div className='flex items-center space-x-2'>
                      <RadioGroupItem value='auto' id='auto' />
                      <Label htmlFor='auto'>自动更新</Label>
                    </div>
                  </RadioGroup>
                </div>
                <div className='flex-1'></div>
                {updateMode === 'auto' && (
                  <div className='justify-center items-center'>
                    <label className='block mb-2'>更新间隔 (秒)</label>
                    <Input
                      type='number'
                      className='w-40 h-10'
                      value={
                        (
                          dataSource.executor as
                            | PythonSourceExecutor
                            | SQLSourceExecutor
                        ).updateMode?.type === 'auto'
                          ? (
                              dataSource.executor as
                                | PythonSourceExecutor
                                | SQLSourceExecutor
                            ).updateMode.interval
                          : 300
                      }
                      onChange={(e) => {
                        const value = parseInt(e.target.value) || 60;
                        setDataSource((prev) => ({
                          ...prev,
                          executor: {
                            ...(prev.executor as
                              | PythonSourceExecutor
                              | SQLSourceExecutor),
                            updateMode: {
                              type: 'auto',
                              interval: value,
                            },
                          },
                        }));
                      }}
                      min={60}
                      step={60}
                    />
                  </div>
                )}
              </div>
            </>
          )}

          {showCSVUploader && (
            <div>
              <label className='block mb-2'>
                {executorType === 'csv_data' ? 'CSV 数据' : '示例 CSV 数据'}
              </label>

              <div className='px-2'>
                {(dataSource.executor?.type === 'csv_data' &&
                  dataSource.executor.data.length === 0) ||
                (dataSource.executor?.type === 'csv_uploader' &&
                  dataSource.executor.demoData.length === 0) ? (
                  <div className='border-2 border-dashed border-gray-300 rounded-lg p-6 text-center'>
                    <div className='flex flex-col items-center justify-center space-y-4'>
                      <svg
                        xmlns='http://www.w3.org/2000/svg'
                        className='h-12 w-12 text-gray-400'
                        fill='none'
                        viewBox='0 0 24 24'
                        stroke='currentColor'
                      >
                        <path
                          strokeLinecap='round'
                          strokeLinejoin='round'
                          strokeWidth={2}
                          d='M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z'
                        />
                      </svg>
                      <p className='text-gray-600'>
                        {executorType === 'csv_data'
                          ? '请上传 CSV 文件'
                          : '暂无示例 CSV 数据'}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className='flex justify-center items-center'>
                    <CSVTable
                      csvData={
                        dataSource.executor.type === 'csv_data'
                          ? dataSource.executor.data
                          : dataSource.executor.demoData
                      }
                    />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className='mt-auto'>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button
            onClick={handleSave}
            // 判断是否禁用"保存"按钮
            disabled={
              !dataSource.name ||
              dataSource.alias === 'df_' ||
              (dataSource.executor.type === 'sql' &&
                !dataSource.executor.code) ||
              (dataSource.executor.type === 'python' &&
                !dataSource.executor.code) ||
              (dataSource.executor.type === 'csv_data' &&
                !dataSource.executor.data) ||
              (dataSource.executor.type === 'csv_uploader' &&
                !dataSource.executor.demoData)
            }
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
