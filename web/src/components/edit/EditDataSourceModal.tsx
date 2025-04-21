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
import type { EngineChoices } from '@/types/models/engineChoices';
import type { AliasRelianceMap } from '@/types/models/aliasRelianceMap';
import { Download } from 'lucide-react';

import AceEditor from 'react-ace';
import 'ace-builds/src-noconflict/theme-xcode';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/mode-sql';
import { toast } from 'sonner';
import Papa from 'papaparse';

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

  // 方法2：更安全的类型保护
  const updateModeSafe = (
    dataSource.executor as PythonSourceExecutor | SQLSourceExecutor
  ).updateMode;
  const intervalSafe =
    updateModeSafe?.type === 'auto' ? updateModeSafe.interval : 300;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className='max-w-3xl h-[80vh] max-h-[90vh] flex flex-col overflow-hidden'>
        <DialogHeader>
          <DialogTitle>
            {initialDataSource ? '编辑数据源' : '新建数据源'}
          </DialogTitle>
        </DialogHeader>

        <div className='space-y-4 flex-1 overflow-y-auto pr-2'>
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
                    const fileInput = document.createElement('input');
                    fileInput.type = 'file';
                    fileInput.accept = '.csv';
                    fileInput.onchange = (e: any) => {
                      const file = e.target.files[0];
                      if (!file) return;

                      // 文件大小限制（例如：10MB）
                      const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
                      if (file.size > MAX_FILE_SIZE) {
                        toast.error('文件大小不能超过 10MB');
                        return;
                      }

                      // 使用 Papa Parse 解析 CSV 文件
                      Papa.parse(file, {
                        complete: (results) => {
                          // 验证解析结果
                          if (results.errors.length > 0) {
                            toast.error('CSV 文件解析出错');
                            console.error(results.errors);
                            return;
                          }

                          // 验证数据是否为空
                          if (results.data.length <= 1) {
                            toast.error('CSV 文件内容不能为空');
                            return;
                          }

                          // 如果是csv_uploader， 仅保留top 10行数据
                          if (executorType === 'csv_uploader') {
                            results.data = results.data.slice(0, 10 + 1);
                          }

                          // 将解析后的数据转换为 CSV 字符串
                          const csvData = Papa.unparse(results.data);

                          // 根据执行器类型更新数据源
                          setDataSource((prev) => ({
                            ...prev,
                            executor: {
                              ...(prev.executor as
                                | CSVSourceExecutor
                                | CSVUploaderSourceExecutor),
                              ...(executorType === 'csv_data'
                                ? { data: csvData }
                                : { demoData: csvData }),
                            },
                          }));

                          // 提示成功
                          toast.success('CSV 文件上传成功');
                        },
                        error: (error) => {
                          toast.error('CSV 文件解析失败');
                          console.error(error);
                        },
                        skipEmptyLines: true, // 跳过空行
                      });
                    };
                    fileInput.click();
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
                      value={intervalSafe}
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
              <label className='block mb-2 flex items-center justify-between'>
                <span>
                  {executorType === 'csv_data' ? 'CSV 数据' : '示例 CSV 数据'}{' '}
                  {' (仅显示前5行)'}
                </span>
                {((executorType === 'csv_data' &&
                  dataSource.executor?.type === 'csv_data' &&
                  dataSource.executor.data.length > 0) ||
                  (executorType === 'csv_uploader' &&
                    dataSource.executor?.type === 'csv_uploader' &&
                    dataSource.executor.demoData.length > 0)) && (
                  <Button
                    variant='outline'
                    size='sm'
                    onClick={() => {
                      // 获取当前的CSV数据
                      const csvData =
                        executorType === 'csv_data'
                          ? (dataSource.executor as CSVSourceExecutor).data
                          : (dataSource.executor as CSVUploaderSourceExecutor)
                              .demoData;

                      // 创建下载链接
                      const blob = new Blob([csvData], {
                        type: 'text/csv;charset=utf-8;',
                      });
                      const link = document.createElement('a');
                      const url = URL.createObjectURL(blob);

                      // 生成文件名
                      const filename = `${dataSource.name || 'data'}_${
                        executorType === 'csv_data' ? 'dataset' : 'demo'
                      }.csv`;

                      link.setAttribute('href', url);
                      link.setAttribute('download', filename);
                      link.style.visibility = 'hidden';
                      document.body.appendChild(link);
                      link.click();
                      document.body.removeChild(link);
                    }}
                  >
                    <Download className='h-4 w-4 mr-2' />
                    下载 CSV
                  </Button>
                )}
              </label>

              <div className='px-2'>
                {(dataSource.executor?.type === 'csv_data' &&
                  dataSource.executor.data.length === 0) ||
                (dataSource.executor?.type === 'csv_uploader' &&
                  dataSource.executor.demoData.length === 0) ? (
                  <div className='border-2 border-dashed border-gray-300 rounded-lg p-6 text-center'>
                    <div className='flex flex-col items-center justify-center space-y-4'>
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
                          ? (dataSource.executor as CSVSourceExecutor).data
                          : (dataSource.executor as CSVUploaderSourceExecutor)
                              .demoData
                      }
                    />
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className='mt-4 pt-4 sticky bottom-0 bg-white'>
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
