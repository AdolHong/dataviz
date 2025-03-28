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
} from '@/types/models/dataSource';

interface EditDataSourceModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (dataSource: DataSource) => void;
  initialDataSource?: DataSource | null;
}
import AceEditor from 'react-ace';
import 'ace-builds/src-noconflict/theme-xcode';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/mode-sql';

export const EditDataSourceModal = ({
  open,
  onClose,
  onSave,
  initialDataSource = null,
}: EditDataSourceModalProps) => {
  const [dataSource, setDataSource] = useState<Partial<DataSource>>({
    name: '',
    description: '',
    executor: {
      type: 'python',
      engine: 'default',
      code: '',
      updateMode: {
        type: 'manual',
      },
    },
  });

  // 当打开模态框或初始数据源变化时重置表单数据
  useEffect(() => {
    if (initialDataSource) {
      setDataSource({
        id: initialDataSource.id,
        name: initialDataSource.name || '',
        description: initialDataSource.description || '',
        executor: initialDataSource.executor,
      });
    } else {
      // 重置为初始状态
      setDataSource({
        name: '',
        description: '',
        executor: {
          type: 'python',
          engine: 'default',
          code: '',
          updateMode: {
            type: 'manual',
          },
        },
      });
    }
  }, [initialDataSource, open]);

  const handleSave = () => {
    // 简单的验证
    if (!dataSource.name) {
      alert('请输入数据源名称');
      return;
    }

    // 根据执行器类型验证
    if (['python', 'sql'].includes(dataSource.executor?.type || '')) {
      if (
        !(dataSource.executor as PythonSourceExecutor | SQLSourceExecutor).code
      ) {
        alert('请输入代码');
        return;
      }
    } else if (dataSource.executor?.type === 'csv_data') {
      if (!(dataSource.executor as CSVSourceExecutor).data) {
        alert('请上传CSV数据');
        return;
      }
    } else if (dataSource.executor?.type === 'csv_uploader') {
      if (!(dataSource.executor as CSVUploaderSourceExecutor).demoData) {
        alert('请上传示例CSV数据');
        return;
      }
    }

    const finalDataSource: DataSource = {
      id: dataSource.id || Date.now().toString(), // 如果是新建，生成临时ID
      name: dataSource.name || '',
      description: dataSource.description,
      executor: dataSource.executor as
        | PythonSourceExecutor
        | SQLSourceExecutor
        | CSVSourceExecutor
        | CSVUploaderSourceExecutor,
    };

    onSave(finalDataSource);
    onClose();
  };

  // 处理执行器类型变更
  const handleExecutorTypeChange = (type: string) => {
    switch (type) {
      case 'python':
        setDataSource((prev) => ({
          ...prev,
          executor: {
            type: 'python',
            engine: 'default',
            code: '',
            updateMode: {
              type: 'manual',
            },
          },
        }));
        break;
      case 'sql':
        setDataSource((prev) => ({
          ...prev,
          executor: {
            type: 'sql',
            engine: 'default',
            code: '',
            updateMode: {
              type: 'manual',
            },
          },
        }));
        break;
      case 'csv_data':
        setDataSource((prev) => ({
          ...prev,
          executor: {
            type: 'csv_data',
            data: '',
          },
        }));
        break;
      case 'csv_uploader':
        setDataSource((prev) => ({
          ...prev,
          executor: {
            type: 'csv_uploader',
            demoData: '',
          },
        }));
        break;
    }
  };

  // 处理更新模式变更
  const handleUpdateModeChange = (type: 'manual' | 'auto') => {
    if (['python', 'sql'].includes(dataSource.executor?.type || '')) {
      setDataSource((prev) => ({
        ...prev,
        executor: {
          ...(prev.executor as PythonSourceExecutor | SQLSourceExecutor),
          updateMode: {
            type,
            ...(type === 'auto' ? { interval: 600 } : {}),
          },
        },
      }));
    }
  };

  // 获取执行器类型
  const executorType = dataSource.executor?.type || 'python';

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
          <div>
            <label className='block mb-2'>数据源名称</label>
            <Input
              value={dataSource.name || ''}
              onChange={(e) =>
                setDataSource((prev) => ({ ...prev, name: e.target.value }))
              }
              placeholder='输入数据源名称'
            />
          </div>

          <div>
            <label className='block mb-2'>描述（可选）</label>
            <Input
              value={dataSource.description || ''}
              onChange={(e) =>
                setDataSource((prev) => ({
                  ...prev,
                  description: e.target.value,
                }))
              }
              placeholder='输入数据源描述'
            />
          </div>

          <div className='flex space-x-10'>
            <div>
              <label className='block mb-2'>执行器类型</label>
              <Select
                value={executorType}
                onValueChange={handleExecutorTypeChange}
              >
                <SelectTrigger className='w-45'>
                  <SelectValue placeholder='选择执行器类型' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='python'>Python</SelectItem>
                  <SelectItem value='sql'>SQL</SelectItem>
                  <SelectItem value='csv_data'>CSV 数据</SelectItem>
                  <SelectItem value='csv_uploader'>CSV 上传器</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className='flex-1'></div>
            {showCodeEditor && (
              <div>
                <label className='block mb-2'>引擎</label>
                <Select
                  value={
                    (
                      dataSource.executor as
                        | PythonSourceExecutor
                        | SQLSourceExecutor
                    ).engine || 'default'
                  }
                  onValueChange={(engine) =>
                    setDataSource((prev) => ({
                      ...prev,
                      executor: {
                        ...(prev.executor as
                          | PythonSourceExecutor
                          | SQLSourceExecutor),
                        engine,
                      },
                    }))
                  }
                >
                  <SelectTrigger className='w-45'>
                    <SelectValue placeholder='选择引擎' />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='default'>默认</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}

            {showCSVUploader && (
              <div>
                <label className='block mb-2'>
                  {executorType === 'csv_data' ? ' CSV 数据' : ' 示例 CSV 数据'}
                </label>
                <button
                  type='button'
                  className='py-1 h-8 w-45 shadow-sm  rounded-sm hover:bg-blue-100 transition-colors'
                  onClick={() => {
                    // 这里应当触发文件上传，为简化代码，仅模拟
                    const mockData = 'id,name,value\n1,测试,100\n2,示例,200';
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
                  点击上传
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
                      handleUpdateModeChange(value as 'manual' | 'auto')
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
                        ).updateMode?.interval || 600
                      }
                      onChange={(e) =>
                        setDataSource((prev) => ({
                          ...prev,
                          executor: {
                            ...(prev.executor as
                              | PythonSourceExecutor
                              | SQLSourceExecutor),
                            updateMode: {
                              type: 'auto',
                              interval: parseInt(e.target.value) || 600,
                            },
                          },
                        }))
                      }
                      min={1}
                    />
                  </div>
                )}
              </div>
            </>
          )}

          {showCSVUploader && (
            <div>
              <label className='block  mb-2'>
                {executorType === 'csv_data' ? 'CSV 数据' : '示例 CSV 数据'}
              </label>
              <div className='border shadow-sm rounded-md p-8 min-h-40 text-center'>
                <p className='mt-2 text-sm text-gray-500'>
                  {executorType === 'csv_data'
                    ? (dataSource.executor as CSVSourceExecutor)?.data
                      ? '已上传文件'
                      : '支持 .csv 格式文件'
                    : (dataSource.executor as CSVUploaderSourceExecutor)
                          ?.demoData
                      ? '已上传示例文件'
                      : '支持 .csv 格式文件'}
                </p>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className='mt-auto'>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
